import os
import asyncio
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
import uvicorn
import webbrowser
from typing import List
import aiofiles
from termcolor import colored
from pydantic import BaseModel
from llm_service import LLMService
import shutil
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from bs4 import BeautifulSoup
import html2text
import email
import mimetypes
import extract_msg
from email import policy
from email.parser import BytesParser
import jinja2
from io import BytesIO

from dotenv import load_dotenv  
load_dotenv()

# Define request models
class SearchRequest(BaseModel):
    search_terms: List[str]

BATCH_SIZE = 10  # Maximum number of concurrent API calls
SUPPORTED_FORMATS = {'.msg', '.eml'}  # Add supported email formats here

# Define HTML styles - Updated for xhtml2pdf compatibility
HTML_STYLES = '''
<style type="text/css">
    @page {
        size: A4;
        margin: 2cm;
    }
    body {
        font-family: Helvetica, Arial, sans-serif;
        font-size: 11pt;
        line-height: 1.6;
    }
    h1 {
        color: #1e40af;
        font-size: 18pt;
        margin-bottom: 20px;
        padding-bottom: 10px;
        border-bottom: 1px solid #e5e7eb;
    }
    .header {
        margin-bottom: 30px;
        background-color: #f8fafc;
        padding: 15px;
        border-radius: 5px;
    }
    .header p {
        margin: 5px 0;
    }
    .label {
        font-weight: bold;
        color: #333333;
        min-width: 80px;
        display: inline-block;
    }
    .content {
        margin-top: 20px;
    }
    table {
        width: 100%;
        border-collapse: collapse;
        margin: 10px 0;
    }
    th, td {
        border: 1px solid #dddddd;
        padding: 8px;
        text-align: left;
    }
    th {
        background-color: #f5f5f5;
    }
    pre {
        white-space: pre-wrap;
        font-family: Helvetica, Arial, sans-serif;
        background-color: #f8fafc;
        padding: 15px;
        border-radius: 5px;
        margin: 10px 0;
    }
    .email-body {
        line-height: 1.6;
    }
    blockquote {
        border-left: 3px solid #e5e7eb;
        margin: 10px 0;
        padding-left: 10px;
        color: #4b5563;
    }
</style>
'''

# HTML template for PDF generation
# HTML template for PDF generation
PDF_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    {styles}
</head>
<body>
    {content}
</body>
</html>
'''

def convert_html_to_pdf(html_content: str, output_path: str) -> bool:
    """Convert HTML to PDF using xhtml2pdf"""
    try:
        # Ensure the HTML content is properly encoded
        if not isinstance(html_content, str):
            html_content = str(html_content)
        
        # Debugging: Print the HTML content to verify it's correct
        print("HTML Content:", html_content)
        
        # Create a buffer for the PDF
        result_file = BytesIO()
        
        # Convert HTML to PDF
        pisa_status = pisa.CreatePDF(
            src=html_content,  # the HTML to convert
            dest=result_file,  # file handle to receive result
            encoding='utf-8'
        )
        
        # If conversion failed, return False
        if pisa_status.err:
            print(colored(f"PDF conversion failed with {pisa_status.err} errors", "red"))
            return False
            
        # Write the PDF to file
        with open(output_path, 'wb') as output_file:
            output_file.write(result_file.getvalue())
            
        return True
    except Exception as e:
        print(colored(f"Error in PDF conversion: {str(e)}", "red"))
        return False

app = FastAPI()

# Create directories if they don't exist
Path("static").mkdir(exist_ok=True)
Path("templates").mkdir(exist_ok=True)
Path("uploaded_emails").mkdir(exist_ok=True)

# Initialize mimetypes
mimetypes.init()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="templates")

# Initialize services
llm_service = LLMService()

# Initialize Jinja2 environment for email templates
template_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader('templates'),
    autoescape=True
)

async def read_msg_content(file_path: Path) -> dict:
    """Read and parse .msg email content"""
    msg = None
    try:
        msg = extract_msg.Message(str(file_path))
        
        sender = str(msg.sender or "")
        to = str(msg.to or "")
        subject = str(msg.subject or "")
        date = str(msg.date or "")
        body = msg.body or ""
        html_body = msg.htmlBody or ""
        
        # Convert body to string and handle encoding
        if isinstance(body, bytes):
            body = body.decode('utf-8', errors='replace')
        else:
            body = str(body)
            
        # Handle HTML body encoding
        if isinstance(html_body, bytes):
            html_body = html_body.decode('utf-8', errors='replace')

        return {
            "from": sender,
            "to": to,
            "subject": subject,
            "date": date,
            "body": body,
            "html_body": html_body
        }
    except Exception as e:
        print(colored(f"Error reading .msg file {file_path}: {str(e)}", "red"))
        raise
    finally:
        if msg is not None:
            try:
                msg.close()
            except Exception as e:
                print(colored(f"Warning: Error closing msg file: {str(e)}", "yellow"))
    
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    try:
        uploaded_files = []
        for file in files:
            # Check if file extension is supported
            file_extension = Path(file.filename).suffix.lower()
            if file_extension not in SUPPORTED_FORMATS:
                print(colored(f"Skipping {file.filename} - unsupported format", "yellow"))
                continue
                
            file_path = Path("uploaded_emails") / file.filename
            async with aiofiles.open(file_path, 'wb') as f:
                content = await file.read()
                await f.write(content)
            uploaded_files.append(file.filename)
            print(colored(f"Successfully uploaded: {file.filename}", "green"))
            
        return {"status": "success", "uploaded_files": uploaded_files}
    except Exception as e:
        print(colored(f"Error uploading files: {str(e)}", "red"))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze")
async def analyze_emails(search_request: SearchRequest):
    try:
        # Read all supported email formats from the uploaded_emails directory
        emails_dir = Path("uploaded_emails")
        email_files = []
        for format in SUPPORTED_FORMATS:
            email_files.extend(list(emails_dir.glob(f"*{format}")))
        
        emails = []
        for file in email_files:
            try:
                email_data = await read_email_content(file)
                # Format content for analysis
                formatted_content = f"""From: {email_data['from']}
To: {email_data['to']}
Subject: {email_data['subject']}
Date: {email_data['date']}

{email_data['body']}"""
                
                emails.append({
                    "filename": file.name,
                    "subject": email_data['subject'],
                    "content": formatted_content
                })
            except Exception as e:
                print(colored(f"Error processing {file.name}: {str(e)}", "red"))
                continue

        print(colored(f"Found {len(emails)} emails to analyze", "blue"))
        
        # Process email analysis in batches
        print(colored("Starting email analysis in batches...", "blue"))
        analysis_results = await process_emails_in_batches(emails, search_request.search_terms)
        
        print(colored("Analysis complete!", "green"))
        
        return {
            "status": "success",
            "analysis_results": analysis_results,
            "num_emails": len(emails)
        }
    except Exception as e:
        print(colored(f"Error in analysis: {str(e)}", "red"))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/convert-to-pdf/{filename}")
async def convert_to_pdf(filename: str):
    try:
        email_path = Path("uploaded_emails") / filename
        if not email_path.exists():
            raise HTTPException(status_code=404, detail="Email file not found")
            
        # Check if the file is corrupted
        try:
            with open(email_path, 'rb') as f:
                f.read()
        except Exception as e:
            raise HTTPException(status_code=400, detail="Email file is corrupted")
            
        pdf_path = await email_to_pdf(str(email_path))
        return FileResponse(pdf_path, media_type="application/pdf", filename=f"{filename}.pdf")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/view-email/{filename}")
async def view_email(filename: str):
    try:
        email_path = Path("uploaded_emails") / filename
        if not email_path.exists():
            raise HTTPException(status_code=404, detail="Email file not found")
        
        email_data = await read_email_content(email_path)
        return email_data
    except Exception as e:
        print(colored(f"Error viewing email: {str(e)}", "red"))
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/delete-all-emails")
async def delete_all_emails():
    try:
        emails_dir = Path("uploaded_emails")
        files = list(emails_dir.glob("*.*"))
        
        deleted_files = []
        failed_files = []
        
        for file in files:
            try:
                # Try multiple times with a delay
                max_attempts = 3
                for attempt in range(max_attempts):
                    try:
                        file.unlink()
                        deleted_files.append(str(file))
                        break
                    except PermissionError:
                        if attempt < max_attempts - 1:
                            print(colored(f"Attempt {attempt + 1}: File {file} is locked, waiting before retry...", "yellow"))
                            await asyncio.sleep(1)  # Wait 1 second before retrying
                        else:
                            raise
            except Exception as e:
                error_msg = f"Error deleting file {file}: {str(e)}"
                print(colored(error_msg, "red"))
                failed_files.append({"file": str(file), "error": str(e)})
        
        response = {
            "status": "success",
            "deleted_files": deleted_files,
            "failed_files": failed_files
        }
        
        if failed_files:
            response["message"] = f"Deleted {len(deleted_files)} files, {len(failed_files)} files failed to delete"
        else:
            response["message"] = f"Successfully deleted {len(deleted_files)} files"
            
        return response
    except Exception as e:
        print(colored(f"Error in delete_all_emails: {str(e)}", "red"))
        raise HTTPException(status_code=500, detail=str(e))

def open_browser():
    webbrowser.open("http://localhost:8000")

async def read_msg_content(file_path: Path) -> dict:
    """Read and parse .msg email content"""
    msg = None
    try:
        msg = extract_msg.Message(str(file_path))
        
        sender = str(msg.sender or "")
        to = str(msg.to or "")
        subject = str(msg.subject or "")
        date = str(msg.date or "")
        body = msg.body or ""
        html_body = msg.htmlBody or ""
        
        # Convert body to string and handle encoding
        if isinstance(body, bytes):
            body = body.decode('utf-8', errors='replace')
        else:
            body = str(body)
            
        # Handle HTML body encoding
        if isinstance(html_body, bytes):
            html_body = html_body.decode('utf-8', errors='replace')

        # Debugging: Print the email data
        print("Email Data:", {
            "from": sender,
            "to": to,
            "subject": subject,
            "date": date,
            "body": body,
            "html_body": html_body
        })

        return {
            "from": sender,
            "to": to,
            "subject": subject,
            "date": date,
            "body": body,
            "html_body": html_body
        }
    except Exception as e:
        print(colored(f"Error reading .msg file {file_path}: {str(e)}", "red"))
        raise
    finally:
        if msg is not None:
            try:
                msg.close()
            except Exception as e:
                print(colored(f"Warning: Error closing msg file: {str(e)}", "yellow"))

async def read_email_content(file_path: Path) -> dict:
    """Read and parse email content based on file extension"""
    file_extension = file_path.suffix.lower()
    
    if file_extension not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported file format: {file_extension}")
        
    if file_extension == '.msg':
        return await read_msg_content(file_path)
    elif file_extension == '.eml':
        return await read_eml_content(file_path)
    
async def read_eml_content(file_path: Path) -> dict:
    """Read and parse .eml email content"""
    try:
        async with aiofiles.open(file_path, 'rb') as f:
            content = await f.read()
        
        email_message = BytesParser(policy=policy.default).parsebytes(content)
        
        sender = str(email_message.get('From', ''))
        to = str(email_message.get('To', ''))
        subject = str(email_message.get('Subject', ''))
        date = str(email_message.get('Date', ''))
        
        body = ''
        html_body = ''
        
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    body_part = part.get_payload(decode=True)
                    try:
                        body += body_part.decode('utf-8', errors='replace')
                    except Exception:
                        body += body_part.decode('latin-1', errors='replace')
                elif content_type == "text/html":
                    html_part = part.get_payload(decode=True)
                    try:
                        html_body += html_part.decode('utf-8', errors='replace')
                    except Exception:
                        html_body += html_part.decode('latin-1', errors='replace')
        else:
            content_type = email_message.get_content_type()
            payload = email_message.get_payload(decode=True)
            try:
                decoded_content = payload.decode('utf-8', errors='replace')
            except Exception:
                decoded_content = payload.decode('latin-1', errors='replace')
                
            if content_type == "text/html":
                html_body = decoded_content
                # Extract plain text from HTML for body
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html_body, 'html.parser')
                body = soup.get_text()
            else:
                body = decoded_content

        return {
            "from": sender,
            "to": to,
            "subject": subject,
            "date": date,
            "body": body,
            "html_body": html_body
        }
    except Exception as e:
        print(colored(f"Error reading .eml file {file_path}: {str(e)}", "red"))
        raise

async def process_batch(emails_batch: List[dict], search_terms: List[str]) -> List[dict]:
    """Process a batch of emails with concurrent API calls"""
    try:
        print(colored(f"Starting analysis for {len(emails_batch)} emails...", "cyan"))
        tasks = [llm_service.analyze_email_content(email["content"], search_terms) for email in emails_batch]
        
        # Wait for all tasks in this batch to complete
        results = await asyncio.gather(*tasks)
        return results
    except Exception as e:
        print(colored(f"Error processing batch: {str(e)}", "red"))
        raise

async def process_emails_in_batches(emails: List[dict], search_terms: List[str]) -> List[dict]:
    """Process emails in batches of BATCH_SIZE"""
    try:
        results = []
        total_batches = (len(emails) + BATCH_SIZE - 1) // BATCH_SIZE
        
        for i in range(0, len(emails), BATCH_SIZE):
            batch_num = i // BATCH_SIZE + 1
            batch = emails[i:i + BATCH_SIZE]
            print(colored(f"\nProcessing batch {batch_num}/{total_batches} ({len(batch)} emails)...", "blue"))
            
            try:
                batch_results = await process_batch(batch, search_terms)
                for j, result in enumerate(batch_results):
                    email_index = i + j
                    results.append({
                        "filename": emails[email_index]["filename"],
                        "subject": emails[email_index]["subject"],
                        "analysis": result
                    })
                print(colored(f"✓ Batch {batch_num}/{total_batches} completed successfully", "green"))
                
                if batch_num < total_batches:
                    remaining = len(emails) - (i + BATCH_SIZE)
                    print(colored(f"Waiting before starting next batch... ({remaining} emails remaining)", "yellow"))
                    await asyncio.sleep(2)
                
            except Exception as e:
                print(colored(f"Error in batch {batch_num}: {str(e)}", "red"))
                raise
                
        print(colored(f"\nAll {total_batches} batches processed successfully!", "green"))
        return results
    except Exception as e:
        print(colored(f"Error in batch processing: {str(e)}", "red"))
        raise

async def convert_email_to_pdf(email_data: dict, output_path: str) -> bool:
    """Convert email to PDF using reportlab with better table and formatting support"""
    try:
        # Create the PDF document
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )

        # Prepare the story (content elements)
        story = []
        styles = getSampleStyleSheet()
        
        # Create custom styles
        header_style = ParagraphStyle(
            'HeaderStyle',
            parent=styles['Heading1'],
            fontSize=14,
            spaceAfter=20
        )
        
        label_style = ParagraphStyle(
            'LabelStyle',
            parent=styles['Normal'],
            fontSize=10,
            fontName='Helvetica-Bold'
        )
        
        value_style = ParagraphStyle(
            'ValueStyle',
            parent=styles['Normal'],
            fontSize=10
        )

        # Define custom colors
        header_bg_color = colors.Color(red=(0.95), green=(0.95), blue=(0.95))  # Light grey for header

        # Add email header information
        header_data = [
            ['From:', email_data.get('from', 'N/A')],
            ['To:', email_data.get('to', 'N/A')],
            ['Subject:', email_data.get('subject', 'N/A')],
            ['Date:', email_data.get('date', 'N/A')]
        ]

        # Create header table
        header_table = Table(header_data, colWidths=[1*inch, 5*inch])
        header_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('BACKGROUND', (0, 0), (-1, -1), colors.whitesmoke),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 20))

        # Process email body
        body_content = email_data.get('html_body', '') or email_data.get('body', '')
        
        if body_content:
            if email_data.get('html_body'):
                # Parse HTML content
                soup = BeautifulSoup(body_content, 'html.parser')
                
                # Handle tables in HTML
                for table in soup.find_all('table'):
                    # Convert HTML table to reportlab table
                    table_data = []
                    for row in table.find_all('tr'):
                        table_row = []
                        for cell in row.find_all(['td', 'th']):
                            table_row.append(Paragraph(cell.get_text(), value_style))
                        table_data.append(table_row)
                    
                    if table_data:
                        pdf_table = Table(table_data)
                        pdf_table.setStyle(TableStyle([
                            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                            ('FONTSIZE', (0, 0), (-1, -1), 10),
                            ('GRID', (0, 0), (-1, -1), 1, colors.black),
                            ('BACKGROUND', (0, 0), (-1, 0), header_bg_color),
                        ]))
                        story.append(pdf_table)
                        story.append(Spacer(1, 12))
                
                # Convert remaining HTML to text
                h = html2text.HTML2Text()
                h.body_width = 0
                text_content = h.handle(str(soup))
            else:
                text_content = body_content

            # Split content into paragraphs and add to story
            for paragraph in text_content.split('\n\n'):
                if paragraph.strip():
                    story.append(Paragraph(paragraph.replace('\n', '<br/>'), value_style))
                    story.append(Spacer(1, 12))

        # Build the PDF
        doc.build(story)
        return True
    except Exception as e:
        print(colored(f"Error in PDF conversion: {str(e)}", "red"))
        return False

async def email_to_pdf(email_path: str) -> str:
    """Convert email to PDF using enhanced reportlab conversion"""
    try:
        # Get file extension and read email content
        file_extension = Path(email_path).suffix.lower()
        if file_extension not in SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported file format: {file_extension}")

        email_data = await read_email_content(Path(email_path))
        
        # Set output PDF path
        pdf_path = str(email_path).rsplit('.', 1)[0] + '.pdf'
        
        # Convert to PDF using the new conversion function
        if not await convert_email_to_pdf(email_data, pdf_path):
            raise Exception("Failed to convert email to PDF")
        
        return pdf_path
    except Exception as e:
        print(colored(f"Error converting email to PDF: {str(e)}", "red"))
        raise HTTPException(status_code=500, detail=f"Error converting email to PDF: {str(e)}")

if __name__ == "__main__":
    # Open browser after a short delay
    asyncio.get_event_loop().run_in_executor(None, lambda: asyncio.run(asyncio.sleep(1.5)) or open_browser())
    uvicorn.run(app, host="127.0.0.1", port=8000) 