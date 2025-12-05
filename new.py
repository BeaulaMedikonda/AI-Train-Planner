"""
🚆 AI Railway Route Planner - CREWAI WITH REAL API DATA (FIXED)
- Uses RailRadar API for ALL actual train data
- CrewAI analyzes ACTUAL routes (not generic tips)
- Validates Indian destinations
- Progressive search: Direct → 2-leg → 3-leg
"""
from flask import Flask, request, jsonify
from crewai import Agent, Task, Crew, Process
from crewai.tools import tool
import requests
import time
import logging
import sys
from datetime import datetime
from typing import Dict, Optional, List
import re
import json
from openai import OpenAI

app = Flask(__name__)

# ============================================================
#           ENHANCED LOGGING
# ============================================================

class ColoredFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': '\033[36m',
        'INFO': '\033[32m',
        'WARNING': '\033[33m',
        'ERROR': '\033[31m',
    }
    RESET = '\033[0m'

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)

for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(ColoredFormatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.root.addHandler(handler)
logging.root.setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)
logging.getLogger('crewai').setLevel(logging.INFO)

# ============================================================
#                  CONFIG
# ============================================================

OPENAI_API_KEY = "your key"
client = OpenAI(api_key=OPENAI_API_KEY)

BASE = "https://railradar.in/api/v1"
REQUEST_TIMEOUT = 15
RETRY_ATTEMPTS = 3

# Common Indian railway stations for validation
KNOWN_STATIONS = {
    "HYB", "NDLS", "BCT", "MAS", "SBC", "BZA", "HWH", "PNBE", "JP", "NGP",
    "BPL", "AGC", "CNB", "ALD", "JBP", "GWL", "VSKP", "BBS", "PUNE", "LKO"
}

# ============================================================
#                  CORE FUNCTIONS
# ============================================================

def call_railradar(endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
    """Makes API request with retries."""
    url = f"{BASE}{endpoint}"
    params = params or {}

    for attempt in range(RETRY_ATTEMPTS):
        try:
            res = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, dict) and data.get("success"):
                    return data.get("data", {})
        except Exception as e:
            logger.error(f"API error: {e}")

        if attempt < RETRY_ATTEMPTS - 1:
            time.sleep(1)

    return None


def call_openai_api(user_query: str, system_prompt: str) -> str:
    """Calls OpenAI API."""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query}
            ],
            temperature=0.3,
            max_tokens=1000
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return "AI service unavailable."


def validate_station_code(code: str) -> bool:
    """Validates station code format."""
    if not code:
        return False
    code = code.strip().upper()
    return bool(re.match(r'^[A-Z]{2,5}$', code)) and len(code) <= 5


def is_indian_location(location: str) -> bool:
    """Check if location is likely an Indian location using AI."""
    system_prompt = """Determine if this is a valid Indian railway destination.
Return ONLY JSON: {"is_indian": true/false, "reason": "brief explanation"}
Examples:
- "Mumbai" -> {"is_indian": true, "reason": "Major Indian city"}
- "Paris" -> {"is_indian": false, "reason": "City in France"}
- "Hogwarts" -> {"is_indian": false, "reason": "Fictional location"}"""

    result = call_openai_api(f"Location: {location}", system_prompt)
    try:
        parsed = json.loads(result.replace("```json", "").replace("```", "").strip())
        return parsed.get("is_indian", False), parsed.get("reason", "")
    except:
        return False, "Could not validate location"


def find_station_code(location: str) -> Optional[str]:
    """Find station code using AI with validation."""
    logger.info(f"🔍 Finding station code for: {location}")

    location_clean = location.strip().upper()

    # Check if already a valid code
    if validate_station_code(location_clean) and location_clean in KNOWN_STATIONS:
        logger.info(f"   ✅ Known valid code: {location_clean}")
        return location_clean

    # Try to find code via AI
    system_prompt = """Convert Indian city/location name to EXACT official Railway station code.
Examples: Hyderabad→HYB, Mumbai→BCT, Delhi→NDLS, Chennai→MAS, Bangalore→SBC, Vijayawada→BZA
Return ONLY JSON: {"code": "HYB"}"""

    result = call_openai_api(f"Station code for: {location}", system_prompt)
    try:
        parsed = json.loads(result.replace("```json", "").replace("```", "").strip())
        code = parsed.get("code", "").upper()
        if validate_station_code(code):
            # Verify with API
            test = call_railradar("/trains/between", params={"from": code, "to": "NDLS"})
            if test:
                logger.info(f"   ✅ Found and verified: {code}")
                return code
    except:
        pass

    logger.error(f"   ❌ Could not find: {location}")
    return None


def format_duration(minutes: int) -> str:
    """Formats duration."""
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m" if mins else f"{hours}h"


# ============================================================
#        FETCH ALL REAL ROUTES FROM API
# ============================================================

def find_all_real_routes(from_code: str, to_code: str) -> Dict[str, List]:
    """Fetch ONLY real routes from API - progressive search."""
    logger.info(f"🔍 Finding REAL routes: {from_code} → {to_code}")

    routes = {
        "direct": [],
        "connecting_2leg": [],
        "connecting_3leg": []
    }

    # 1. Search direct trains
    logger.info("   📍 Searching DIRECT trains...")
    direct_data = call_railradar("/trains/between", params={"from": from_code, "to": to_code})

    if direct_data and direct_data.get("trains"):
        routes["direct"] = direct_data["trains"][:5]
        logger.info(f"   ✅ Found {len(routes['direct'])} DIRECT trains")
        return routes

    logger.info("   ⚠️ No direct trains found, searching connecting routes...")

    # 2. Search 2-leg routes
    logger.info("   📍 Searching 2-LEG routes...")
    junctions = ["NDLS", "HWH", "MAS", "SBC", "BCT", "BZA", "PNBE", "NGP", "BPL", "JP"]
    junctions = [j for j in junctions if j not in [from_code, to_code]]

    two_leg_routes = []
    for junction in junctions[:10]:
        leg1 = call_railradar("/trains/between", params={"from": from_code, "to": junction})
        if leg1 and leg1.get("trains"):
            leg2 = call_railradar("/trains/between", params={"from": junction, "to": to_code})
            if leg2 and leg2.get("trains"):
                arr_min = leg1["trains"][0].get("toStationSchedule", {}).get("arrivalMinutes", 0)
                dep_min = leg2["trains"][0].get("fromStationSchedule", {}).get("departureMinutes", 0)
                waiting = dep_min - arr_min
                if waiting < 0:
                    waiting += 1440

                if 20 <= waiting <= 720:
                    two_leg_routes.append({
                        "junction": junction,
                        "leg1_train": leg1["trains"][0],
                        "leg2_train": leg2["trains"][0],
                        "waiting_mins": waiting
                    })
                    logger.info(f"      ✅ Found 2-leg via {junction}")

                    if len(two_leg_routes) >= 3:
                        break

    routes["connecting_2leg"] = two_leg_routes
    if two_leg_routes:
        logger.info(f"   ✅ Found {len(two_leg_routes)} 2-LEG routes")

    return routes


# ============================================================
#                    CREWAI TOOLS (ANALYSIS ONLY)
# ============================================================

@tool
def analyze_actual_routes_tool(routes_summary: str) -> str:
    """Analyze REAL routes data and provide specific recommendations based on actual trains found.

    Args:
        routes_summary: A summary of routes with train details

    Returns:
        Specific analysis and recommendation
    """
    logger.info("🔧 TOOL: Analyzing actual route data")

    try:
        # Parse the routes summary text
        lines = routes_summary.strip().split('\n')

        analysis = []

        # Check if direct trains mentioned
        if "direct_trains" in routes_summary.lower() and "duration_mins" in routes_summary:
            analysis.append("DIRECT TRAINS AVAILABLE:")

            # Extract direct train info from summary
            import re
            train_nums = re.findall(r'"number":\s*"([^"]+)"', routes_summary)
            durations = re.findall(r'"duration_mins":\s*(\d+)', routes_summary)

            if train_nums and durations:
                for num, dur_str in zip(train_nums[:3], durations[:3]):
                    dur = int(dur_str)
                    analysis.append(f"  • Train {num}: {dur//60}h {dur%60}m")

                best_dur = min([int(d) for d in durations[:3]])
                best_num = train_nums[durations.index(str(best_dur))]
                analysis.append(f"\nRECOMMENDATION: Train {best_num} is the fastest direct option at {best_dur//60}h {best_dur%60}m.")
            else:
                analysis.append("Multiple direct trains available. Choose based on your preferred departure time.")

        elif "connecting_2leg" in routes_summary.lower():
            analysis.append("NO DIRECT TRAINS - CONNECTING ROUTES AVAILABLE:")

            # Extract connection info
            import re
            vias = re.findall(r'"via":\s*"([^"]+)"', routes_summary)
            leg1_durs = re.findall(r'"leg1_duration":\s*(\d+)', routes_summary)
            leg2_durs = re.findall(r'"leg2_duration":\s*(\d+)', routes_summary)
            waits = re.findall(r'"waiting_mins":\s*(\d+)', routes_summary)

            if vias and leg1_durs:
                for i, via in enumerate(vias[:2]):
                    if i < len(leg1_durs) and i < len(leg2_durs) and i < len(waits):
                        leg1 = int(leg1_durs[i])
                        leg2 = int(leg2_durs[i])
                        wait = int(waits[i])
                        total = leg1 + leg2 + wait
                        analysis.append(f"  • Via {via}: Total {total//60}h {total%60}m (includes {wait//60}h {wait%60}m layover)")

                if vias:
                    analysis.append(f"\nRECOMMENDATION: Connection via {vias[0]} offers a balanced journey with reasonable layover time.")
            else:
                analysis.append("Multiple connecting routes available through major junctions.")

        else:
            analysis.append("Route information is being processed. Please refer to the route options for details.")

        return "\n".join(analysis) if analysis else "Unable to analyze route data. Please check route options."

    except Exception as e:
        logger.error(f"   ❌ Analysis error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return "Route analysis in progress. Please refer to the detailed route options provided."


# ============================================================
#                    CREWAI AGENTS & WORKFLOW
# ============================================================

def create_agents():
    """Create CrewAI agents for analysis."""

    logger.info("👥 CREATING CREWAI AGENTS...")

    intent_parser = Agent(
        role="Query Intent Parser",
        goal="Extract from/to locations from user query",
        backstory="Expert at parsing natural language queries about train routes.",
        verbose=True,
        allow_delegation=False
    )
    logger.info("   ✅ Agent 1: Intent Parser")

    route_analyzer = Agent(
        role="Route Analysis Expert",
        goal="Analyze ACTUAL route data from RailRadar API and provide specific recommendations",
        backstory="Expert at analyzing real railway data and recommending optimal journeys based on actual train schedules, durations, and connections.",
        tools=[analyze_actual_routes_tool],
        verbose=True,
        allow_delegation=False
    )
    logger.info("   ✅ Agent 2: Route Analyzer")

    travel_advisor = Agent(
        role="Travel Experience Specialist",
        goal="Provide specific travel tips based on the actual recommended route",
        backstory="Expert at advising travelers with practical tips based on their specific journey.",
        verbose=True,
        allow_delegation=False
    )
    logger.info("   ✅ Agent 3: Travel Advisor")

    return intent_parser, route_analyzer, travel_advisor


def create_tasks(query: str, routes_data: Dict, agents: tuple):
    """Create tasks for agents."""

    logger.info("📋 CREATING TASKS...")

    intent_parser, route_analyzer, travel_advisor = agents

    task1 = Task(
        description=f"Parse this query and extract FROM and TO locations: '{query}'",
        agent=intent_parser,
        expected_output="Extracted from and to locations"
    )

    # Create detailed routes description for analysis
    routes_details = {
        "direct_count": len(routes_data.get("direct", [])),
        "direct_trains": [
            {
                "number": t.get("trainNumber"),
                "name": t.get("trainName"),
                "duration_mins": t.get("travelTimeMinutes"),
                "distance_km": t.get("distanceKm")
            } for t in routes_data.get("direct", [])[:3]
        ],
        "connecting_2leg_count": len(routes_data.get("connecting_2leg", [])),
        "connecting_2leg_routes": [
            {
                "via": r["junction"],
                "leg1": r["leg1_train"].get("trainNumber"),
                "leg2": r["leg2_train"].get("trainNumber"),
                "leg1_duration": r["leg1_train"].get("travelTimeMinutes"),
                "leg2_duration": r["leg2_train"].get("travelTimeMinutes"),
                "waiting_mins": r["waiting_mins"]
            } for r in routes_data.get("connecting_2leg", [])[:2]
        ]
    }

    task2 = Task(
        description=f"""Analyze these ACTUAL train routes found from RailRadar API:
        
{json.dumps(routes_details, indent=2)}

Provide specific analysis of these actual trains - which is fastest, which has best timing, etc.""",
        agent=route_analyzer,
        expected_output="Specific analysis of actual routes with clear recommendation",
        context=[task1]
    )

    task3 = Task(
        description="Based on the SPECIFIC route recommended, provide targeted travel tips for that particular journey type (direct vs connecting, duration, etc).",
        agent=travel_advisor,
        expected_output="Practical travel tips specific to the recommended route",
        context=[task2]
    )

    return [task1, task2, task3]


# ============================================================
#                    FORMAT OUTPUT
# ============================================================

def format_response(from_code: str, to_code: str, routes_data: Dict, crew_result: str) -> Dict:
    """Format response with REAL data."""

    response = {
        "success": True,
        "journey": {
            "from": from_code,
            "to": to_code,
            "searchDate": datetime.now().strftime("%d %B %Y"),
        },
        "routeOptions": [],
        "totalOptions": 0,
        "aiRecommendation": {"reason": crew_result},
        "timestamp": datetime.now().isoformat()
    }

    # Add direct trains
    for idx, train in enumerate(routes_data.get("direct", [])[:5], 1):
        response["routeOptions"].append({
            "option": idx,
            "type": "🚂 DIRECT",
            "trainNumber": train.get("trainNumber"),
            "trainName": train.get("trainName"),
            "duration": format_duration(train.get("travelTimeMinutes", 0)),
            "distance": f"{train.get('distanceKm', 0)} km"
        })

    # Add 2-leg routes
    for idx, route in enumerate(routes_data.get("connecting_2leg", [])[:3], len(response["routeOptions"]) + 1):
        leg1_dur = route["leg1_train"].get("travelTimeMinutes", 0)
        leg2_dur = route["leg2_train"].get("travelTimeMinutes", 0)
        total_dur = leg1_dur + leg2_dur + route["waiting_mins"]

        response["routeOptions"].append({
            "option": idx,
            "type": "🔄 2-LEG",
            "via": route["junction"],
            "leg1Train": f"{route['leg1_train'].get('trainNumber')} ({format_duration(leg1_dur)})",
            "leg2Train": f"{route['leg2_train'].get('trainNumber')} ({format_duration(leg2_dur)})",
            "layover": format_duration(route["waiting_mins"]),
            "totalDuration": format_duration(total_dur)
        })

    response["totalOptions"] = len(response["routeOptions"])

    return response


# ============================================================
#                    FLASK ENDPOINTS
# ============================================================

@app.before_request
def log_request():
    print(f"\n{'='*110}")
    print(f"📨 REQUEST: {request.method} {request.path}")
    print(f"{'='*110}")
    sys.stdout.flush()


@app.after_request
def log_response(response):
    print(f"📤 RESPONSE: {response.status_code}\n")
    sys.stdout.flush()
    return response


@app.get("/")
def home():
    return jsonify({
        "service": "🚆 Railway Route Planner WITH CREWAI (FIXED)",
        "version": "8.0-FIXED",
        "features": [
            "✅ REAL data from RailRadar API only",
            "✅ CrewAI analyzes ACTUAL routes (not generic tips)",
            "✅ Validates Indian destinations",
            "✅ Polite rejection for non-Indian locations",
            "✅ Progressive search (Direct → 2-leg)"
        ]
    })


@app.get("/health")
def health():
    return jsonify({"status": "✅ Healthy", "version": "8.0", "timestamp": datetime.now().isoformat()})


@app.post("/api/smart_query")
def smart_query():
    """Main endpoint."""

    if not request.is_json:
        return jsonify({"error": "Must be JSON"}), 400

    query = request.json.get("query", "").strip()
    if not query:
        return jsonify({"error": "Missing query"}), 400

    logger.info(f"🚀 QUERY: {query}")
    print(f"{'='*110}\n")

    try:
        # Step 1: Extract locations
        logger.info("📍 STEP 1: Extracting locations from query...")
        system_prompt = """Extract FROM and TO locations from train query.
Return ONLY JSON: {"from": "Hyderabad", "to": "Vijayawada"}"""

        result = call_openai_api(query, system_prompt)
        parsed = json.loads(result.replace("```json", "").replace("```", "").strip())

        from_loc = parsed.get("from", "").strip()
        to_loc = parsed.get("to", "").strip()

        logger.info(f"   FROM: {from_loc}, TO: {to_loc}")

        # Step 2: Validate Indian locations
        logger.info("📍 STEP 2: Validating locations...")
        from_is_indian, from_reason = is_indian_location(from_loc)
        to_is_indian, to_reason = is_indian_location(to_loc)

        if not from_is_indian or not to_is_indian:
            logger.warning(f"   ⚠️ Non-Indian location detected")
            return jsonify({
                "success": False,
                "error": "Non-Indian destination",
                "message": f"I apologize, but I can only help with train routes within India. "
                          f"{'The origin location' if not from_is_indian else 'The destination'} "
                          f"'{from_loc if not from_is_indian else to_loc}' "
                          f"appears to be {from_reason if not from_is_indian else to_reason}. "
                          f"If you're looking for Indian train routes, please specify cities within India.",
                "timestamp": datetime.now().isoformat()
            }), 400

        # Step 3: Find station codes
        logger.info("📍 STEP 3: Finding station codes...")
        from_code = find_station_code(from_loc)
        to_code = find_station_code(to_loc)

        if not from_code or not to_code:
            logger.error("   ❌ Could not find station codes")
            return jsonify({
                "success": False,
                "error": "Station not found",
                "message": f"I couldn't find the railway station code for "
                          f"{'origin' if not from_code else 'destination'} "
                          f"'{from_loc if not from_code else to_loc}'. "
                          f"Please check the spelling or try a major nearby city.",
                "timestamp": datetime.now().isoformat()
            }), 400

        logger.info(f"   Codes: {from_code} → {to_code}")

        # Step 4: Fetch REAL routes
        logger.info("📍 STEP 4: Fetching REAL routes from RailRadar API...")
        routes_data = find_all_real_routes(from_code, to_code)

        total_routes = (len(routes_data.get("direct", [])) +
                       len(routes_data.get("connecting_2leg", [])))

        if total_routes == 0:
            logger.warning("   ⚠️ No routes found")
            return jsonify({
                "success": False,
                "error": "No routes found",
                "message": f"Unfortunately, I couldn't find any train routes between {from_loc} and {to_loc}. "
                          f"This might be because there are no direct connections, or the stations are not well connected. "
                          f"You may need to consider alternative transportation or check major nearby cities.",
                "timestamp": datetime.now().isoformat()
            }), 404

        logger.info(f"   ✅ Found {total_routes} REAL routes total")

        # Step 5: CrewAI analysis on REAL data
        logger.info("📍 STEP 5: Running CrewAI analysis on actual routes...")
        print(f"{'='*110}\n")

        agents = create_agents()
        tasks = create_tasks(query, routes_data, agents)

        crew = Crew(agents=list(agents), tasks=tasks, process=Process.sequential, verbose=True)
        crewai_result = crew.kickoff()

        print(f"\n{'='*110}\n")
        logger.info("✅ CrewAI analysis complete")

        # Format final response
        response = format_response(from_code, to_code, routes_data, str(crewai_result))

        return jsonify(response)

    except Exception as e:
        logger.error(f"❌ ERROR: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": "Internal error",
            "message": "An unexpected error occurred while processing your request. Please try again.",
            "timestamp": datetime.now().isoformat()
        }), 500


if __name__ == "__main__":
    print("\n" + "="*110)
    print("🚆 RAILWAY ROUTE PLANNER - CREWAI WITH REAL API DATA (FIXED)")
    print("="*110)
    print("\n📊 IMPROVEMENTS:")
    print("   ✅ CrewAI analyzes ACTUAL routes (not generic tips)")
    print("   ✅ Validates Indian destinations")
    print("   ✅ Polite rejection for foreign/fictional places")
    print("   ✅ Accurate distance/duration from API")
    print("\n⚡ DATA FLOW:")
    print("   → Validate Indian locations")
    print("   → Fetch REAL routes from RailRadar API")
    print("   → CrewAI analyzes SPECIFIC trains found")
    print("   → Recommend based on ACTUAL data")
    print("\n" + "="*110 + "\n")
    sys.stdout.flush()

    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False, threaded=True)