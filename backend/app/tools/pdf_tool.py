# backend/app/tools/pdf_tool.py
import os
import re
from crewai.tools import BaseTool
from typing import ClassVar, List
import pypdfium2 as pdfium
import fitz  # PyMuPDF
from PIL import Image
import pytesseract
from pdf2image import convert_from_path, pdfinfo_from_path
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class PDFProcessingTool(BaseTool):
    name: str = "PDF Content and Image Extractor"
    description: str = (
        "Extracts text content and images from a given PDF file. "
        "Input should be the path to the PDF file. "
        "Automatically attempts OCR on pages with minimal text. "
        "Saves extracted images and embeds them as Markdown links."
    )
    # Define a threshold for considering a page as potentially image-based
    MIN_TEXT_LENGTH_FOR_NO_OCR: ClassVar[int] = 50 # If text length is less than this, consider OCR

    # These will be instance attributes, not Pydantic fields of the BaseTool model itself.
    _image_output_dir_absolute: str
    _static_images_url_path: str

    def __init__(self, image_output_dir_param: str, static_images_url_path_param: str, **kwargs):
        """
        Initializes the tool with paths for image handling.
        Args:
            image_output_dir_param: Absolute path to save extracted images.
            static_images_url_path_param: Base URL path for serving these images (e.g., /static/images).
        """
        super().__init__(**kwargs)
        self._image_output_dir_absolute = image_output_dir_param
        self._static_images_url_path = static_images_url_path_param
        
        # Ensure the image directory exists and is writable
        try:
            os.makedirs(self._image_output_dir_absolute, exist_ok=True)
            # Test write permissions
            test_file = os.path.join(self._image_output_dir_absolute, "test.txt")
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
            logger.info(f"Successfully verified write permissions for: {self._image_output_dir_absolute}")
        except Exception as e:
            logger.error(f"Failed to create or verify image directory: {e}")
            raise
        
        logger.info(f"PDFProcessingTool initialized with:")
        logger.info(f"Image output directory: {self._image_output_dir_absolute}")
        logger.info(f"Static images URL path: {self._static_images_url_path}")

    def _extract_images_with_pymupdf(self, pdf_file_path: str, page_index: int, pdf_filename_base: str) -> List[str]:
        """
        Extract images from a PDF page using PyMuPDF.
        Returns a list of markdown image links.
        """
        markdown_image_links = []
        try:
            pdf_file = fitz.open(pdf_file_path)
            page = pdf_file.load_page(page_index)
            image_list = page.get_images(full=True)

            if image_list:
                logger.info(f"Found {len(image_list)} images on page {page_index + 1}")
                
                for image_index, img in enumerate(image_list, start=1):
                    try:
                        xref = img[0]
                        base_image = pdf_file.extract_image(xref)
                        image_bytes = base_image["image"]
                        image_ext = base_image["ext"]

                        # Save the image
                        image_filename = f"{pdf_filename_base}_page{page_index+1}_img{image_index}.{image_ext}"
                        image_save_path = os.path.join(self._image_output_dir_absolute, image_filename)
                        
                        logger.debug(f"Attempting to save image to: {image_save_path}")
                        
                        # Ensure the directory exists
                        os.makedirs(os.path.dirname(image_save_path), exist_ok=True)
                        
                        # Save the image
                        with open(image_save_path, "wb") as image_file:
                            image_file.write(image_bytes)
                        
                        # Verify the file was saved
                        if os.path.exists(image_save_path):
                            file_size = os.path.getsize(image_save_path)
                            logger.info(f"Successfully saved image: {image_filename} (size: {file_size} bytes)")
                        else:
                            logger.error(f"Failed to save image: {image_filename}")
                            continue

                        # Create markdown link
                        image_url = f"{self._static_images_url_path}/{image_filename}"
                        markdown_link = f"\n\n![Page {page_index+1} Image {image_index}]({image_url})\n"
                        markdown_image_links.append(markdown_link)
                        logger.debug(f"Created markdown link: {markdown_link}")

                    except Exception as e_img:
                        error_msg = f"Error processing image {image_index} on page {page_index + 1}: {e_img}"
                        logger.error(error_msg)
                        markdown_image_links.append(f"\n[Error processing image {image_index} on page {page_index + 1}: {e_img}]\n")

            pdf_file.close()
            return markdown_image_links

        except Exception as e:
            error_msg = f"Error in PyMuPDF image extraction for page {page_index + 1}: {e}"
            logger.error(error_msg)
            return [f"\n[Error in image extraction for page {page_index + 1}: {e}]\n"]

    def _run(self, pdf_file_path: str, force_ocr_all_pages: bool = False, force_ocr_pages: List[int] = None) -> str:
        """
        Extracts text and images from a PDF, attempting OCR on image-like pages.
        Args:
            pdf_file_path: Path to the PDF file.
            force_ocr_all_pages: Boolean, if True, forces OCR on all pages.
            force_ocr_pages: Optional list of page numbers (0-indexed) to force OCR on.
        Returns:
            Extracted text content and image links as a single string.
        """
        if not os.path.exists(pdf_file_path):
            error_msg = f"Error: PDF file not found at the specified path: {pdf_file_path}"
            logger.error(error_msg)
            return error_msg

        if force_ocr_pages is None:
            force_ocr_pages = []

        pdf_filename_base = os.path.splitext(os.path.basename(pdf_file_path))[0]
        pdf_filename_base = re.sub(r'[^\w_.-]', '_', pdf_filename_base)
        
        logger.info(f"Processing PDF: {pdf_file_path}")
        logger.info(f"Base filename for images: {pdf_filename_base}")
        
        full_document_content_parts = []

        try:
            try:
                pdfinfo_from_path(pdf_file_path, poppler_path=None)
            except Exception as pe:
                print(f"Poppler/pdf2image check failed: {pe}. Ensure Poppler is installed and in PATH.")
                if "Unable to get page count" in str(pe) or "No output received from Poppler" in str(pe):
                    return f"Error: Poppler (PDF rendering utility) not found or not working correctly. Please ensure it's installed and in your system's PATH. Original error: {pe}"

            pdf = pdfium.PdfDocument(pdf_file_path)
            n_pages = len(pdf)

            for i in range(n_pages):
                page_content_parts = []
                page_text_content = ""
                perform_ocr_on_this_page = False

                # 1. Try direct text extraction
                page = pdf.get_page(i)
                textpage = page.get_textpage()
                try:
                    extracted_text_direct = textpage.get_text_bounded()
                except AttributeError:
                    try:
                        extracted_text_direct = textpage.get_text_range()
                    except AttributeError:
                        extracted_text_direct = str(textpage)
                
                page_text_content = extracted_text_direct.strip()

                # 2. Decide if OCR is needed for this page
                if force_ocr_all_pages:
                    perform_ocr_on_this_page = True
                    print(f"Forcing OCR on page {i+1} as per force_ocr_all_pages flag.")
                elif force_ocr_pages and i in force_ocr_pages:
                    perform_ocr_on_this_page = True
                    print(f"Forcing OCR on page {i+1} as per force_ocr_pages list.")
                elif len(page_text_content) < self.MIN_TEXT_LENGTH_FOR_NO_OCR:
                    try:
                        text_objects = textpage.get_text_objects()
                        if len(text_objects) > 0:
                            print(f"Page {i+1} has minimal direct text (length: {len(page_text_content)}). Attempting OCR.")
                            perform_ocr_on_this_page = True
                        else:
                            print(f"Page {i+1} has minimal direct text but also appears to have no objects. Skipping OCR.")
                    except AttributeError:
                        if not page_text_content:
                            print(f"Page {i+1} has no text content. Attempting OCR.")
                            perform_ocr_on_this_page = True
                        else:
                            print(f"Page {i+1} has minimal text content. Skipping OCR.")

                # 3. Perform OCR if decided
                if perform_ocr_on_this_page:
                    try:
                        print(f"Attempting OCR on page {i+1}...")
                        images = convert_from_path(pdf_file_path, first_page=i+1, last_page=i+1, dpi=300)
                        if images:
                            pil_image = images[0].convert('L')
                            ocr_text = pytesseract.image_to_string(pil_image, lang='eng').strip()
                            if ocr_text:
                                print(f"OCR successful for page {i+1}. Length: {len(ocr_text)}")
                                if len(page_text_content) < self.MIN_TEXT_LENGTH_FOR_NO_OCR:
                                    page_text_content = ocr_text
                                else:
                                    page_text_content += "\n\n--- OCR Text ---\n" + ocr_text
                            else:
                                print(f"OCR for page {i+1} yielded no text.")
                        else:
                            page_text_content += f"\n[OCR attempted but no image returned for page {i+1}]"
                    except Exception as e:
                        ocr_error_msg = f"\n[OCR error on page {i+1}: {str(e)}]"
                        page_text_content += ocr_error_msg
                        print(ocr_error_msg)

                if page_text_content:
                    page_content_parts.append(page_text_content)

                # 4. Extract images using PyMuPDF
                image_links = self._extract_images_with_pymupdf(pdf_file_path, i, pdf_filename_base)
                page_content_parts.extend(image_links)

                if page_content_parts:
                    full_document_content_parts.append(f"\n--- Page {i+1} ---\n" + "\n".join(filter(None, page_content_parts)))
                else:
                    full_document_content_parts.append(f"\n--- Page {i+1} --- (Blank or no extractable content)")

            return "\n".join(full_document_content_parts)

        except Exception as e:
            import traceback
            logger.error(f"Error processing PDF: {str(e)}")
            logger.error(traceback.format_exc())
            return f"Error processing PDF: {str(e)}"
