# 🚆 AI Railway Route Planner (CrewAI + Real API Data)

An intelligent **Indian Railway Route Planner** built using **Flask, CrewAI, OpenAI, and RailRadar API**.  
This system fetches **real-time Indian train route data** and uses **AI agents** to provide smart, data-backed travel recommendations.

---

## ✅ Key Features

- ✅ Uses **real data from RailRadar API**
- ✅ **CrewAI agents analyze actual train routes**
- ✅ **Indian destination validation** (rejects foreign/fictional places)
- ✅ **Progressive route search**
  - Direct trains
  - 2-leg connecting trains
- ✅ Smart AI-based **fastest & best route recommendation**
- ✅ Clean **JSON API output** for frontend/mobile integration
- ✅ Production-style **logging & validation**

---

## 🛠 Tech Stack

- Python  
- Flask  
- CrewAI  
- OpenAI API  
- RailRadar API  
- Requests  

---

## 📁 Project Structure

```
ai-railway-route-planner/
│
├── app.py
├── requirements.txt
├── .gitignore
├── README.md
└── .venv/   (ignored)
```

---

## ⚙️ Setup & Installation

### 1️⃣ Clone the Repository
```bash
git clone https://github.com/YOUR_USERNAME/ai-railway-route-planner.git
cd ai-railway-route-planner
```

### 2️⃣ Create Virtual Environment
```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
```

### 3️⃣ Install Dependencies
```bash
pip install -r requirements.txt
```

### 4️⃣ Set OpenAI API Key (IMPORTANT)
```bash
setx OPENAI_API_KEY "your_openai_api_key_here"
```
Restart the terminal after setting the key.

### 5️⃣ Run the Application
```bash
python app.py
```

Server will start at:
```
http://localhost:5000
```

---

## 📡 API Usage

### 🔹 Health Check
```http
GET /health
```

### 🔹 Smart Route Query
```http
POST /api/smart_query
Content-Type: application/json
```

#### Example Request
```json
{
  "query": "Hyderabad to Vijayawada"
}
```

#### Example Response (Sample)
```json
{
  "success": true,
  "journey": {
    "from": "HYB",
    "to": "BZA"
  },
  "routeOptions": [
    {
      "option": 1,
      "type": "🚂 DIRECT",
      "trainNumber": "12727",
      "duration": "6h 10m"
    }
  ],
  "aiRecommendation": {
    "reason": "Fastest direct train based on real API data."
  }
}
```

---

## 🧠 AI Workflow

1. Extracts **source and destination** using AI  
2. Validates **Indian locations only**  
3. Fetches **real train data from RailRadar API**  
4. CrewAI **analyzes actual routes and trains**  
5. Returns **optimized journey recommendation**

---

## 🔐 Security Best Practices

- OpenAI API key is **never hardcoded**
- API key is loaded using **environment variables**
- `.gitignore` excludes:
  - `.venv`
  - `.env`
  - Logs
  - Cache files

---

## 🚀 Future Improvements

- 3-leg route support
- Frontend UI integration
- Ticket fare prediction
- Seat availability checking
- User authentication

---

## 👩‍💻 Author

**Beaula Medikonda**  
Aspiring AI Engineer & Data Scientist  
---

## ⭐ If you like this project, give it a star on GitHub!
