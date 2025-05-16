import flet as ft
import httpx # For making HTTP requests to the backend
import os
import tempfile # For handling file downloads if needed
import json # For parsing JSON responses

# Global variable to store the backend URL (can be configured)
BACKEND_API_URL = "http://localhost:8000/api/v1/convert" # Your FastAPI backend endpoint

# --- Flet Application Main Function ---
def main(page: ft.Page):
    page.title = "PDF to Markdown Converter (Flet)"
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.theme_mode = ft.ThemeMode.LIGHT # Or DARK
    page.padding = 20
    page.scroll = ft.ScrollMode.ADAPTIVE # Allow scrolling if content overflows

    # --- State Management (using page.session for simplicity, or create a class) ---
    if not page.session.get("gemini_api_key"):
        page.session.set("gemini_api_key", "")
    if not page.session.get("selected_pdf_path"):
        page.session.set("selected_pdf_path", None)
    if not page.session.get("selected_pdf_name"):
        page.session.set("selected_pdf_name", None)

    # --- UI Controls ---

    # API Key Input
    api_key_field = ft.TextField(
        label="Gemini API Key",
        password=True,
        can_reveal_password=True,
        value=page.session.get("gemini_api_key"),
        width=400,
        on_change=lambda e: page.session.set("gemini_api_key", e.control.value)
    )

    # File Picker
    def on_file_picked(e: ft.FilePickerResultEvent):
        if e.files and len(e.files) > 0:
            picked_file = e.files[0]
            page.session.set("selected_pdf_path", picked_file.path)
            page.session.set("selected_pdf_name", picked_file.name)
            file_name_display.value = f"Selected: {picked_file.name}"
            status_text.value = f"PDF '{picked_file.name}' selected. Ready to convert."
            # Clear previous results
            markdown_output_text.value = ""
            image_gallery.controls.clear()
            download_button.disabled = True
            page.update()
        else:
            page.session.set("selected_pdf_path", None)
            page.session.set("selected_pdf_name", None)
            file_name_display.value = "No PDF selected."
            status_text.value = "File selection cancelled or no file picked."
            page.update()

    file_picker = ft.FilePicker(on_result=on_file_picked)
    page.overlay.append(file_picker) # Required for FilePicker to work

    pick_file_button = ft.ElevatedButton(
        "Select PDF",
        icon=ft.icons.UPLOAD_FILE,
        on_click=lambda _: file_picker.pick_files(
            allow_multiple=False,
            allowed_extensions=["pdf"]
        ),
    )
    file_name_display = ft.Text("No PDF selected.", italic=True)

    # Status Display
    status_text = ft.Text("Please set API Key and select a PDF.", color=ft.colors.BLUE_GREY_400)
    processing_indicator = ft.ProgressRing(width=24, height=24, stroke_width=3, visible=False)

    # Markdown Output Display
    markdown_output_text = ft.Markdown(
        "", # Initial content
        selectable=True,
        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB, # For good Markdown rendering
        code_theme="atom-one-dark",
        auto_follow_links=True,
        width=700, # Adjust as needed
    )
    
    # Image Gallery
    image_gallery = ft.Row(
        wrap=True, 
        spacing=10, 
        run_spacing=10,
        alignment=ft.MainAxisAlignment.CENTER,
        visible=False # Initially hidden
    )

    # Download Button
    download_button = ft.ElevatedButton(
        "Download Markdown",
        icon=ft.icons.DOWNLOAD,
        disabled=True,
        # on_click will be set later when content is available
    )

    # --- Event Handlers ---
    async def convert_pdf_clicked(e):
        api_key = page.session.get("gemini_api_key")
        pdf_path = page.session.get("selected_pdf_path")
        pdf_name = page.session.get("selected_pdf_name")

        if not api_key:
            status_text.value = "Error: Gemini API Key is missing."
            status_text.color = ft.colors.RED_ACCENT_700
            page.update()
            return
        if not pdf_path:
            status_text.value = "Error: No PDF file selected."
            status_text.color = ft.colors.RED_ACCENT_700
            page.update()
            return

        status_text.value = f"Processing '{pdf_name}'..."
        status_text.color = ft.colors.BLUE_700
        processing_indicator.visible = True
        convert_button.disabled = True
        markdown_output_text.value = "" # Clear previous output
        image_gallery.controls.clear()
        image_gallery.visible = False
        download_button.disabled = True
        page.update()

        try:
            # Prepare file for upload
            files = {'pdf_file': (pdf_name, open(pdf_path, 'rb'), 'application/pdf')}
            headers = {'gemini-api-key': api_key}

            async with httpx.AsyncClient(timeout=300.0) as client: # Increased timeout for potentially long processing
                response = await client.post(BACKEND_API_URL, files=files, headers=headers)
            
            response.raise_for_status() # Will raise an exception for 4XX/5XX errors
            result_data = response.json()

            if result_data.get("error"):
                status_text.value = f"Backend Error: {result_data['error']}"
                status_text.color = ft.colors.RED_ACCENT_700
                markdown_output_text.value = f"## Error\n\n{result_data['error']}"
            else:
                raw_md = result_data.get("raw_markdown_content", "# No content received")
                markdown_output_text.value = raw_md
                status_text.value = "Conversion successful!"
                status_text.color = ft.colors.GREEN_700
                
                # Store content for download
                page.session.set("markdown_to_download", raw_md)
                page.session.set("markdown_filename", f"{os.path.splitext(pdf_name)[0]}.md")
                download_button.disabled = False

                # Display images
                image_urls = result_data.get("image_urls", [])
                if image_urls:
                    image_gallery.controls.clear()
                    for img_url in image_urls:
                        # Assuming image_urls are relative to the backend's static serving
                        # e.g., /static/images/image.png
                        # The backend_url needs to be prepended if not already absolute
                        full_img_url = f"http://localhost:8000{img_url}" if img_url.startswith("/static") else img_url
                        image_gallery.controls.append(
                            ft.Image(
                                src=full_img_url,
                                width=150,
                                height=150,
                                fit=ft.ImageFit.CONTAIN,
                                error_content=ft.Text(f"Error loading: {os.path.basename(img_url)}", size=10)
                            )
                        )
                    image_gallery.visible = True
                else:
                    image_gallery.visible = False


        except httpx.HTTPStatusError as http_err:
            error_detail = f"HTTP error occurred: {http_err.response.status_code} - {http_err.response.text}"
            status_text.value = error_detail
            status_text.color = ft.colors.RED_ACCENT_700
            markdown_output_text.value = f"## HTTP Error\n\n{error_detail}"
            print(f"HTTP error: {http_err} - Response: {http_err.response.text}")
        except Exception as ex:
            error_detail = f"An unexpected error occurred: {str(ex)}"
            status_text.value = error_detail
            status_text.color = ft.colors.RED_ACCENT_700
            markdown_output_text.value = f"## Application Error\n\n{error_detail}"
            print(f"Unexpected error: {ex}")
        finally:
            processing_indicator.visible = False
            convert_button.disabled = False
            page.update()

    convert_button = ft.ElevatedButton(
        "Convert to Markdown",
        icon=ft.icons.TRANSFORM,
        on_click=convert_pdf_clicked,
        bgcolor=ft.colors.BLUE_ACCENT_700,
        color=ft.colors.WHITE,
        height=50
    )

    def on_download_click(e):
        # Get the filename from session storage with proper error handling
        try:
            md_filename = page.session.get("markdown_filename")
            if not md_filename:
                md_filename = "converted.md"
            elif not md_filename.endswith(".md"):
                md_filename += ".md"
        except Exception as ex:
            print(f"Error getting filename from session: {ex}")
            md_filename = "converted.md"
        
        # Ensure we have content to save
        try:
            content = page.session.get("markdown_to_download")
            if not content:
                status_text.value = "No content to save. Please convert a PDF first."
                status_text.color = ft.colors.AMBER_700
                page.update()
                return
        except Exception as ex:
            print(f"Error getting content from session: {ex}")
            status_text.value = "Error accessing saved content. Please try converting again."
            status_text.color = ft.colors.RED_ACCENT_700
            page.update()
            return
            
        try:
            save_file_dialog.save_file(
                dialog_title="Save Markdown As...",
                file_name=md_filename,
                allowed_extensions=["md"]
            )
        except Exception as ex:
            error_msg = f"Error opening save dialog: {str(ex)}"
            status_text.value = error_msg
            status_text.color = ft.colors.RED_ACCENT_700
            print(f"Save dialog error: {error_msg}")
            page.update()

    def save_markdown_file(e: ft.FilePickerResultEvent):
        if e.path:
            try:
                # Get content from session with proper error handling
                try:
                    content_to_save = page.session.get("markdown_to_download")
                except Exception as ex:
                    print(f"Error getting content from session: {ex}")
                    content_to_save = None

                if content_to_save:
                    # Ensure the directory exists
                    os.makedirs(os.path.dirname(e.path), exist_ok=True)
                    
                    # Write the content with proper encoding
                    with open(e.path, "w", encoding="utf-8") as f:
                        f.write(content_to_save)
                    
                    # Show success message
                    status_text.value = f"Markdown saved successfully to: {e.path}"
                    status_text.color = ft.colors.GREEN_700
                else:
                    status_text.value = "No content to save. Please convert a PDF first."
                    status_text.color = ft.colors.AMBER_700
            except Exception as ex_save:
                error_msg = f"Error saving file: {str(ex_save)}"
                status_text.value = error_msg
                status_text.color = ft.colors.RED_ACCENT_700
                print(f"Save error: {error_msg}")
            page.update()

    save_file_dialog = ft.FilePicker(on_result=save_markdown_file)
    page.overlay.append(save_file_dialog)

    download_button.on_click = on_download_click


    # --- Page Layout ---
    page.add(
        ft.Column(
            [
                ft.Text("PDF to Markdown Converter", size=32, weight=ft.FontWeight.BOLD, color=ft.colors.BLUE_GREY_800),
                ft.Text("Upload your PDF, provide your Gemini API Key, and convert!", size=16, color=ft.colors.BLUE_GREY_600),
                ft.Divider(height=20),
                
                ft.Text("1. Configure API Key", size=18, weight=ft.FontWeight.W_600),
                api_key_field,
                ft.Divider(height=20),

                ft.Text("2. Select PDF File", size=18, weight=ft.FontWeight.W_600),
                ft.Row([pick_file_button, file_name_display], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Divider(height=20),
                
                ft.Text("3. Convert", size=18, weight=ft.FontWeight.W_600),
                ft.Row([convert_button, processing_indicator], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                status_text,
                ft.Divider(height=30),

                ft.Text("4. Results", size=18, weight=ft.FontWeight.W_600),
                ft.Container(
                    content=markdown_output_text,
                    border=ft.border.all(1, ft.colors.OUTLINE),
                    border_radius=ft.border_radius.all(5),
                    padding=10,
                    margin=ft.margin.symmetric(vertical=10),
                    bgcolor=ft.colors.SURFACE_VARIANT, # Light background for markdown
                ),
                image_gallery, # Row for images
                download_button,
            ],
            spacing=15,
            alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            scroll=ft.ScrollMode.AUTO, # Enable scrolling for the main column
            expand=True # Allow column to expand
        )
    )
    page.update()

# --- Run the Flet app ---
# To run as a web app: flet run main.py -w
# To run as a desktop app: flet run main.py
if __name__ == "__main__":
    ft.app(target=main) 
    # For web deployment, you might use:
    # ft.app(target=main, view=ft.WEB_BROWSER, port=8550) # Example for web
    # Or deploy using `flet publish main.py` after `flet create .`

