# backend/app/main.py
import os
import shutil
import uuid
import re 
import logging
from fastapi import FastAPI, File, UploadFile, HTTPException, Header
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

from crewai import Agent, Task, Crew, Process, LLM
from app.tools.pdf_tool import PDFProcessingTool 

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# --- Pydantic Schemas ---
class ConversionResponse(BaseModel):
    message: str
    markdown_file_url: Optional[str] = None
    image_urls: Optional[List[str]] = None
    raw_markdown_content: Optional[str] = None
    error: Optional[str] = None

# --- Application Setup ---
app = FastAPI(
    title="PDF to Markdown Service (Simplified)",
    description="Converts PDF files to Markdown using CrewAI and Gemini.",
    version="0.1.0"
)

# --- CORS Configuration ---
origins = [
    "http://localhost",      
    "http://localhost:3000", 
    "http://localhost:5173", 
    "http://localhost:8550",
    "http://127.0.0.1",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8550",
    # Add your frontend production URL here
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Static File and Directory Setup ---
APP_ROOT_DIR = os.path.dirname(os.path.abspath(__file__)) 
BACKEND_ROOT_DIR = os.path.dirname(APP_ROOT_DIR) 

STATIC_DIR_NAME = "static"
IMAGES_DIR_NAME = "images"
MARKDOWN_DIR_NAME = "markdown_outputs"
TEMP_UPLOADS_DIR_NAME = "temp_uploads"

STATIC_PATH_ABS = os.path.join(APP_ROOT_DIR, STATIC_DIR_NAME)
IMAGES_PATH_ABS = os.path.join(STATIC_PATH_ABS, IMAGES_DIR_NAME)
MARKDOWN_PATH_ABS = os.path.join(STATIC_PATH_ABS, MARKDOWN_DIR_NAME)
TEMP_UPLOADS_PATH_ABS = os.path.join(BACKEND_ROOT_DIR, TEMP_UPLOADS_DIR_NAME) 

# Create and verify directories
for directory in [STATIC_PATH_ABS, IMAGES_PATH_ABS, MARKDOWN_PATH_ABS, TEMP_UPLOADS_PATH_ABS]:
    try:
        os.makedirs(directory, exist_ok=True)
        # Test write permissions
        test_file = os.path.join(directory, "test.txt")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        logger.info(f"Successfully created and verified directory: {directory}")
    except Exception as e:
        logger.error(f"Failed to create or verify directory {directory}: {e}")
        raise

STATIC_URL_PATH = f"/{STATIC_DIR_NAME}"
IMAGES_URL_PATH = f"{STATIC_URL_PATH}/{IMAGES_DIR_NAME}"
MARKDOWN_URL_PATH = f"{STATIC_URL_PATH}/{MARKDOWN_DIR_NAME}"

app.mount(STATIC_URL_PATH, StaticFiles(directory=STATIC_PATH_ABS), name="static")
logger.info(f"Mounted static files from: {STATIC_PATH_ABS} at URL: {STATIC_URL_PATH}")


# --- Helper Function for CrewAI Processing ---
def process_pdf_with_crew(pdf_file_path: str, user_gemini_api_key: str) -> dict:
    current_env_gemini_key = os.environ.get("GEMINI_API_KEY")
    os.environ["GEMINI_API_KEY"] = user_gemini_api_key

    output_data = {
        "markdown_file_url": None, 
        "image_urls": [],          
        "raw_markdown_content": None,
        "error": None
    }

    try:
        crew_llm = LLM(
            model='gemini/gemini-1.5-flash-latest', 
            api_key=os.environ["GEMINI_API_KEY"]
        )
        logger.info("CrewAI LLM initialized for request.")

        pdf_tool_instance = PDFProcessingTool(
            image_output_dir_param=IMAGES_PATH_ABS,       
            static_images_url_path_param=IMAGES_URL_PATH  
        )

        pdf_analyzer = Agent(
            role='PDF Content Analyst',
            goal='Accurately extract all text content and images (as links) from the given PDF file. Utilize OCR for pages that are primarily scanned images. If the PDF processing tool returns an error message, output that error message directly.',
            backstory="Expert in digital document processing. Extracts text directly, identifies and links images, and uses OCR for scanned pages to capture textual content. Critically, if the underlying PDF tool fails and returns an error string, this agent's primary goal becomes to report that exact error.",
            tools=[pdf_tool_instance],
            llm=crew_llm, verbose=True, allow_delegation=False, max_iter=7
        )
        structure_identifier = Agent(
            role='Document Structure Semantic Analyzer',
            goal='Identify the logical structure (headings, paragraphs, lists, tables, code blocks) of extracted PDF content. If the input content is an error message from a previous step, output that error message directly.',
            backstory="AI with deep understanding of document layouts. It can infer structure from mixed content (text, OCR, image links) and preserve image links in their correct positions. If it receives an input that starts with 'Error:', it understands this is a propagated error and its task is to pass this error message on.",
            llm=crew_llm, verbose=True, allow_delegation=False, max_iter=10
        )
        markdown_converter = Agent(
            role='Markdown Conversion Specialist',
            goal='Convert structurally annotated content into clean, well-formatted Markdown. For images (including equations), the primary representation is the image link. If the input content is an error message from a previous step, output that error message directly.',
            backstory="Meticulous AI excelling at generating perfect, standard-compliant Markdown. It ensures that text is well-formatted and pre-existing Markdown image links are correctly integrated. If it receives an input that starts with 'Error:', it understands this is a propagated error and its task is to pass this error message on.",
            llm=crew_llm, verbose=True, allow_delegation=False, max_iter=10
        )
        logger.info("CrewAI Agents defined for request.")

        # --- Task Definitions (with updated expected_output for error propagation) ---
        task_extract = Task(
            description=f"Extract text content and images from the PDF located at '{pdf_file_path}'. The tool will attempt OCR for text on full scanned pages if direct text extraction yields little. Images should be saved and represented as Markdown links in the output (e.g., ![]({IMAGES_URL_PATH}/image.png)). Ensure all readable text (embedded or via full-page OCR) and all image references are captured.",
            expected_output=f"A single string containing all extracted text from the PDF (including full-page OCR results where applicable) and Markdown links for any extracted images (e.g., ![]({IMAGES_URL_PATH}/image.png)). Page breaks should be noted. If the PDF processing tool encounters an unrecoverable error, output the exact error message string provided by the tool (it will likely start with 'Error:').",
            agent=pdf_analyzer,
        )
        task_structure = Task(
            description="Analyze the provided content (output of PDF extraction) and identify its logical structure. Determine headings, paragraphs, lists, tables, and code blocks. Preserve Markdown image links in their correct relative positions. If the input from the previous task is an error message (e.g., starts with 'Error:'), then your output should be that exact error message.",
            expected_output="The original content, including Markdown image links, annotated or structured to clearly define elements (e.g., using XML-like tags or clear textual cues). If the input was an error message, output that exact error message.",
            agent=structure_identifier, context=[task_extract]
        )
        task_convert = Task(
            description=f"Take the structurally annotated content and convert it into well-formatted Markdown. Ensure existing Markdown image links (e.g., ![]({IMAGES_URL_PATH}/image.png)) are preserved. For visual elements like equations that are image links, ensure the link is present. Represent tables as Markdown tables. If the input from the previous task is an error message (e.g., starts with 'Error:'), then your output should be that exact error message.",
            expected_output="A single string containing the final, clean Markdown representation of the document, including embedded images via Markdown links. If the input was an error message, output that exact error message.",
            agent=markdown_converter, context=[task_structure]
        )
        logger.info("CrewAI Tasks defined for request.")

        pdf_crew = Crew(
            agents=[pdf_analyzer, structure_identifier, markdown_converter],
            tasks=[task_extract, task_structure, task_convert],
            process=Process.sequential, verbose=True, memory=False
        )
        logger.info("CrewAI crew created. Kicking off...")

        crew_result_obj = pdf_crew.kickoff()
        
        final_markdown_content = ""
        # Prioritize getting the direct result string from the CrewOutput object
        if hasattr(crew_result_obj, 'result') and crew_result_obj.result is not None: 
            final_markdown_content = str(crew_result_obj.result)
        elif hasattr(crew_result_obj, 'raw_output') and isinstance(crew_result_obj.raw_output, str): # Fallback
            final_markdown_content = crew_result_obj.raw_output
        elif isinstance(crew_result_obj, str): # If kickoff itself returned a string
            final_markdown_content = crew_result_obj
        else: # Last resort
            final_markdown_content = str(crew_result_obj)


        # Check if the direct output (hopefully the specific error now) indicates a problem
        if final_markdown_content.strip().startswith("Error:") or "unable to process" in final_markdown_content.lower():
            output_data["error"] = final_markdown_content.strip() # Use the direct error message
            logger.info(f"Propagated error from crew: {output_data['error']}") 
            return output_data
        elif not final_markdown_content.strip():
            output_data["error"] = "Crew execution returned empty content."
            logger.info(output_data["error"])
            return output_data
        
        output_data["raw_markdown_content"] = final_markdown_content

        pdf_basename = os.path.splitext(os.path.basename(pdf_file_path))[0]
        safe_basename = re.sub(r'[^\w_.-]', '_', pdf_basename)
        md_filename = f"{safe_basename}_{uuid.uuid4().hex[:8]}.md"
        
        markdown_file_abs_path = os.path.join(MARKDOWN_PATH_ABS, md_filename)

        with open(markdown_file_abs_path, "w", encoding="utf-8") as f:
            f.write(final_markdown_content)
        
        output_data["markdown_file_url"] = f"{MARKDOWN_URL_PATH}/{md_filename}"
        logger.info(f"Markdown file saved to: {markdown_file_abs_path}")
        logger.info(f"Markdown URL: {output_data['markdown_file_url']}")

        img_pattern = r"!\[.*?\]\((" + re.escape(IMAGES_URL_PATH) + r"/[^\)]+)\)"
        found_image_urls = re.findall(img_pattern, final_markdown_content)
        output_data["image_urls"] = list(set(found_image_urls))
        logger.info(f"Found image URLs in markdown: {output_data['image_urls']}")

    except Exception as e:
        import traceback
        traceback.print_exc()
        output_data["error"] = f"Failed to process PDF with CrewAI: {str(e)}"
    finally:
        if current_env_gemini_key is not None:
            os.environ["GEMINI_API_KEY"] = current_env_gemini_key
        elif "GEMINI_API_KEY" in os.environ: 
            del os.environ["GEMINI_API_KEY"]
        logger.info("GEMINI_API_KEY environment variable handled for request scope.")
    return output_data

# --- API Endpoint ---
@app.post("/api/v1/convert", response_model=ConversionResponse)
async def convert_pdf_endpoint(
    gemini_api_key: str = Header(..., description="User's Gemini API Key"),
    pdf_file: UploadFile = File(..., description="PDF file to be converted.")
):
    if not pdf_file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF files are accepted.")

    if not gemini_api_key or not gemini_api_key.strip():
        raise HTTPException(status_code=400, detail="Gemini API key is required.")

    original_filename = pdf_file.filename
    safe_filename_base = re.sub(r'[^\w_.-]', '_', os.path.splitext(original_filename)[0])
    temp_pdf_filename = f"{uuid.uuid4().hex}_{safe_filename_base}.pdf"
    temp_pdf_path = os.path.join(TEMP_UPLOADS_PATH_ABS, temp_pdf_filename)
    
    generated_files_to_clean = [] 

    try:
        with open(temp_pdf_path, "wb") as buffer:
            shutil.copyfileobj(pdf_file.file, buffer)
        logger.info(f"Temporarily saved uploaded PDF to: {temp_pdf_path}")
        generated_files_to_clean.append(temp_pdf_path)

        result = process_pdf_with_crew(pdf_file_path=temp_pdf_path, user_gemini_api_key=gemini_api_key)

        if result.get("error"):
            logger.info(f"Error from process_pdf_with_crew to be sent to client: {result.get('error')}")
            raise HTTPException(status_code=500, detail=result.get("error"))

        # Add generated markdown and image files to cleanup list
        if result.get("markdown_file_url"):
            md_filename = os.path.basename(result["markdown_file_url"])
            md_abs_path = os.path.join(MARKDOWN_PATH_ABS, md_filename)
            generated_files_to_clean.append(md_abs_path)
        
        if result.get("image_urls"):
            for img_url in result["image_urls"]:
                img_filename = os.path.basename(img_url)
                img_abs_path = os.path.join(IMAGES_PATH_ABS, img_filename)
                generated_files_to_clean.append(img_abs_path)

        return ConversionResponse(
            message="PDF processed successfully.",
            markdown_file_url=result.get("markdown_file_url"),
            image_urls=result.get("image_urls"),
            raw_markdown_content=result.get("raw_markdown_content")
        )
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")
    finally:
        # Clean up temporary files
        for file_path in generated_files_to_clean:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Cleaned up temporary file: {file_path}")
            except Exception as e_clean:
                logger.error(f"Error cleaning up file {file_path}: {e_clean}")


@app.get("/", tags=["Root"])
async def read_root():
    return {"message": "Welcome to the PDF to Markdown Conversion Service!"}

# To run this app: uvicorn app.main:app --reload --port 8000
