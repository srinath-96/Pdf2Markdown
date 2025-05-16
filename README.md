# Pdf2Markdown

A powerful PDF to Markdown conversion tool that leverages LLMs and OCR capabilities to handle both text-based and scanned PDFs, including mathematical equations.

## 🌟 Features

- **Intelligent Text Extraction**: Automatically extracts text content from PDFs using multiple methods
- **OCR Integration**: Handles scanned PDFs and image-based content using Tesseract OCR
- **Image Processing**: Extracts and preserves images from PDFs, including mathematical equations
- **Modern Web Interface**: Built with Flet for a responsive and user-friendly experience
- **FastAPI Backend**: Robust and scalable API for PDF processing
- **CrewAI Integration**: Utilizes AI agents for intelligent content analysis and structure preservation

## 🚀 Tech Stack

- **Frontend**: Flet (Python-based UI framework)
- **Backend**: FastAPI
- **PDF Processing**: 
  - PyPDFium2
  - PyMuPDF (fitz)
  - pdf2image
- **OCR**: Tesseract
- **AI/ML**: 
  - CrewAI
  - Google Gemini Pro
- **Image Processing**: Pillow (PIL)

## 📋 Prerequisites

- Python 3.9+
- Tesseract OCR
- Poppler
- Google Gemini API Key

## 🛠️ Installation

1. Clone the repository:
```bash
git clone https://github.com/srinath-96/Pdf2Markdown.git
cd Pdf2Markdown
```

2. Create and activate a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Install system dependencies:
- **Tesseract OCR**: Required for OCR functionality
- **Poppler**: Required for PDF processing

## 🏃‍♂️ Running the Application

1. Start the FastAPI backend:
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

2. Start the Flet frontend:
```bash
cd flet_frontend
python main.py
```

3. Access the application:
- Frontend: http://localhost:8550
- Backend API: http://localhost:8000

## 🔧 Configuration

1. Set up your Google Gemini API key:
   - Obtain an API key from Google AI Studio
   - The key will be requested when using the application

2. Configure static directories:
   - The application automatically creates necessary directories for images and markdown outputs
   - Default paths:
     - Images: `backend/app/static/images/`
     - Markdown: `backend/app/static/markdown_outputs/`

## 📝 Usage

1. Open the web interface
2. Enter your Gemini API key
3. Upload a PDF file
4. Click "Convert to Markdown"
5. Download the generated markdown file

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.




