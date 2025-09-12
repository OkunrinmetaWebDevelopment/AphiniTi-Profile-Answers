# Profile Answers API

A FastAPI backend service for managing AI question answers with Firebase authentication and Firestore database integration.

## Features

- Save and retrieve AI question answers
- Firebase authentication with ID token verification
- Real-time data synchronization with Firestore
- RESTful API endpoints with comprehensive error handling
- Data validation using Pydantic models
- Answer statistics and progress tracking

## Prerequisites

- Python 3.13 or higher
- Firebase project with Firestore enabled
- Firebase service account key

## Project Setup

### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd profile-answers
```

### 2. Create Virtual Environment

```bash
# Install dependencies and create virtual environment automatically
poetry install

# Activate the Poetry shell (virtual environment)
poetry shell
```

### 3. Install Dependencies

```bash
pip install -e .
```

### 4. Firebase Configuration

#### Step 1: Create Firebase Project
1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Create a new project or select existing one
3. Enable Firestore Database
4. Go to Project Settings > Service Accounts
5. Click "Generate new private key" to download the service account JSON file

#### Step 2: Configure Service Account
1. Create a `config` directory in your project root:
   ```bash
   mkdir config
   ```
2. Place your service account key file in the config directory
3. Rename it to `firebase-service-account.json`

#### Step 3: Update Firebase Configuration
In `main.py`, update the credentials path:
```python
cred = credentials.Certificate("config/firebase-service-account.json")
```

### 5. Environment Variables (Optional)

Create a `.env` file for environment-specific configurations:

```env
# Server Configuration
HOST=0.0.0.0
PORT=8000
DEBUG=True

# Firebase Configuration
FIREBASE_SERVICE_ACCOUNT_PATH=config/firebase-service-account.json

# Logging
LOG_LEVEL=INFO
```

### 6. Firestore Security Rules

Configure Firestore security rules in Firebase Console:

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // AI Answers collection - users can only access their own data
    match /ai_answers/{userId} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }
  }
}
```

## Running the Application

### Development Mode

```bash
# Using Poetry (recommended)
poetry run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Or if you're in the Poetry shell
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Production Mode

```bash
poetry run uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

The API will be available at:
- **API**: http://localhost:8000
- **Interactive Documentation**: http://localhost:8000/docs
- **ReDoc Documentation**: http://localhost:8000/redoc

## API Endpoints

### Authentication
All endpoints require a Firebase ID token in the Authorization header:
```
Authorization: Bearer <firebase-id-token>
```

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/ai-answers` | Save AI question answers |
| GET | `/api/ai-answers` | Retrieve saved answers |
| DELETE | `/api/ai-answers` | Delete all answers |
| PUT | `/api/ai-answers/{question_id}` | Update single answer |
| GET | `/api/ai-answers/stats` | Get answer statistics |
| GET | `/health` | Health check |

### Example Usage

#### Save Answers
```bash
curl -X POST "http://localhost:8000/api/ai-answers" \
  -H "Authorization: Bearer <firebase-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "answers": {
      "1": "I value honesty and communication",
      "2": "Travel, hiking, reading"
    }
  }'
```

#### Retrieve Answers
```bash
curl -X GET "http://localhost:8000/api/ai-answers" \
  -H "Authorization: Bearer <firebase-token>"
```

## Data Structure

### Firestore Collection: `ai_answers`

```json
{
  "ai_answers/{user_id}": {
    "answers": {
      "1": "User's answer to question 1",
      "2": "User's answer to question 2"
    },
    "user_id": "firebase_user_id",
    "created_at": "2024-01-01T12:00:00Z",
    "updated_at": "2024-01-01T12:30:00Z",
    "total_questions": 2
  }
}
```

### Request/Response Models

#### Save Answers Request
```json
{
  "answers": {
    "1": "Answer to question 1",
    "2": "Answer to question 2"
  }
}
```

#### Response Format
```json
{
  "success": true,
  "message": "AI answers saved successfully",
  "answers": {
    "1": "Answer to question 1",
    "2": "Answer to question 2"
  },
  "saved_at": "2024-01-01T12:00:00Z",
  "updated_at": "2024-01-01T12:00:00Z"
}
```

## Development

### Project Structure

```
profile-answers/
├── main.py                 # FastAPI application
├── config/
│   └── firebase-service-account.json
├── pyproject.toml         # Dependencies and project config
├── README.md              # This file
├── .env                   # Environment variables (optional)
└── .gitignore             # Git ignore file
```

### Adding New Endpoints

1. Define Pydantic models for request/response
2. Add endpoint function with proper authentication
3. Include error handling and logging
4. Update documentation

### Testing

Create a test client:

```python
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
```

## Deployment

### Docker (Recommended)

Create `Dockerfile`:

```dockerfile
FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install -e .

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run:
```bash
docker build -t profile-answers-api .
docker run -p 8000:8000 profile-answers-api
```

### Cloud Deployment

The application is ready for deployment on:
- Google Cloud Run
- AWS Lambda (with Mangum adapter)
- Heroku
- Railway
- Vercel

## Security Considerations

1. **Firebase Authentication**: All endpoints verify Firebase ID tokens
2. **Data Isolation**: Users can only access their own data
3. **Input Validation**: All inputs are validated using Pydantic
4. **Error Handling**: Sensitive information is not exposed in error messages
5. **CORS**: Configure CORS for production use

## Troubleshooting

### Common Issues

1. **Firebase Authentication Error**
   - Verify service account key path
   - Check token expiry
   - Ensure proper token format

2. **Firestore Permission Denied**
   - Check Firestore security rules
   - Verify user authentication
   - Ensure proper collection structure

3. **Module Import Errors**
   - Verify all dependencies are installed
   - Check Python version compatibility

### Logging

Check application logs for detailed error information:
```bash
tail -f logs/app.log
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues and questions:
- Create an issue in the repository
- Check the documentation at `/docs`
- Review the logs for error details