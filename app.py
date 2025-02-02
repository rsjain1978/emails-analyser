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
from fpdf import FPDF
import email
import mimetypes
import extract_msg  # Add this import for .msg files

from dotenv import load_dotenv  
load_dotenv()


BATCH_SIZE = 10  # Maximum number of concurrent API calls

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

class SearchRequest(BaseModel):
    search_terms: List[str]

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

async def email_to_pdf(email_path: str) -> str:
    """Convert email to PDF"""
    try:
        # Read email file
        with open(email_path, 'r', encoding='utf-8') as f:
            email_content = f.read()
            
        # Parse email
        email_message = email.message_from_string(email_content)
        
        # Create PDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        
        # Add headers
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, "Email Details", ln=True)
        pdf.set_font("Arial", size=12)
        
        headers = [
            ("From", email_message["from"]),
            ("To", email_message["to"]),
            ("Subject", email_message["subject"]),
            ("Date", email_message["date"])
        ]
        
        for header, value in headers:
            if value:
                pdf.set_font("Arial", 'B', 12)
                pdf.cell(20, 10, f"{header}:", 0)
                pdf.set_font("Arial", size=12)
                pdf.cell(0, 10, value, ln=True)
        
        # Add body
        pdf.ln(10)
        pdf.set_font("Arial", size=12)
        body = email_message.get_payload()
        pdf.multi_cell(0, 10, body)
        
        # Save PDF
        pdf_path = email_path.replace('.eml', '.pdf')
        pdf.output(pdf_path)
        
        return pdf_path
    except Exception as e:
        print(colored(f"Error converting email to PDF: {str(e)}", "red"))
        raise HTTPException(status_code=500, detail="Error converting email to PDF")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    try:
        uploaded_files = []
        for file in files:
            # Check if file is an email file based on extension
            mime_type, _ = mimetypes.guess_type(file.filename)
            is_text = mime_type == 'text/plain'
            is_email = file.filename.lower().endswith(('.eml', '.msg'))
            
            if not (is_text or is_email):
                continue
                
            file_path = Path("uploaded_emails") / file.filename
            async with aiofiles.open(file_path, 'wb') as f:
                content = await file.read()
                await f.write(content)
            uploaded_files.append(file.filename)
            
        return {"status": "success", "uploaded_files": uploaded_files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def read_email_content(file_path: Path) -> dict:
    """Read and parse email content based on file extension"""
    try:
        file_ext = file_path.suffix.lower()
        
        if file_ext == '.msg':
            # Handle .msg files using extract_msg
            msg = extract_msg.Message(str(file_path))
            # Ensure proper encoding of msg content
            try:
                body = msg.body
                if body is None:
                    body = ""
                # Handle potential encoding issues
                if isinstance(body, bytes):
                    body = body.decode('utf-8', errors='replace')
                elif not isinstance(body, str):
                    body = str(body)
            except Exception as e:
                print(colored(f"Error decoding msg body: {str(e)}", "yellow"))
                body = "[Error: Could not decode email body]"

            return {
                "from": str(msg.sender or ""),
                "to": str(msg.to or ""),
                "subject": str(msg.subject or ""),
                "date": str(msg.date or ""),
                "body": body
            }
        else:
            # Handle .eml and .txt files
            async with aiofiles.open(file_path, mode='r', encoding='utf-8', errors='replace') as f:
                content = await f.read()
                email_message = email.message_from_string(content)
                
                # Handle potential multipart messages
                if email_message.is_multipart():
                    body = ""
                    for part in email_message.walk():
                        if part.get_content_type() == "text/plain":
                            try:
                                part_body = part.get_payload(decode=True).decode('utf-8', errors='replace')
                                body += part_body + "\n"
                            except Exception as e:
                                print(colored(f"Error decoding email part: {str(e)}", "yellow"))
                                continue
                else:
                    try:
                        body = email_message.get_payload(decode=True).decode('utf-8', errors='replace')
                    except:
                        body = email_message.get_payload()

                return {
                    "from": str(email_message.get("from", "")),
                    "to": str(email_message.get("to", "")),
                    "subject": str(email_message.get("subject", "")),
                    "date": str(email_message.get("date", "")),
                    "body": body
                }
    except Exception as e:
        print(colored(f"Error reading email {file_path}: {str(e)}", "red"))
        raise

@app.post("/analyze")
async def analyze_emails(search_request: SearchRequest):
    try:
        # Read all emails from the uploaded_emails directory
        emails_dir = Path("uploaded_emails")
        email_files = []
        for ext in ['.eml', '.msg', '.txt']:
            email_files.extend(emails_dir.glob(f'*{ext}'))
        
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
        files = list(emails_dir.glob("*.*")) + list(emails_dir.glob("*.txt"))
        
        for file in files:
            try:
                file.unlink()
            except Exception as e:
                print(colored(f"Error deleting file {file}: {str(e)}", "red"))
        
        return {"status": "success", "message": "All emails deleted successfully"}
    except Exception as e:
        print(colored(f"Error deleting emails: {str(e)}", "red"))
        raise HTTPException(status_code=500, detail=str(e))

def open_browser():
    webbrowser.open("http://localhost:8000")

if __name__ == "__main__":
    # Open browser after a short delay
    asyncio.get_event_loop().run_in_executor(None, lambda: asyncio.run(asyncio.sleep(1.5)) or open_browser())
    uvicorn.run(app, host="127.0.0.1", port=8000) 