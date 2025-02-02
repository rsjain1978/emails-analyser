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
    """Convert .msg email to PDF"""
    try:
        if not str(email_path).lower().endswith('.msg'):
            raise ValueError("Only .msg files are supported")

        # Read email content
        email_data = await read_email_content(Path(email_path))
        
        # Create PDF
        pdf = FPDF()
        pdf.add_page()
        
        # Set font for the whole document
        pdf.set_font("Arial", size=12)
        
        # Add title
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, "Email Details", ln=True)
        pdf.ln(5)
        
        # Add headers
        headers = [
            ("From", email_data["from"]),
            ("To", email_data["to"]),
            ("Subject", email_data["subject"]),
            ("Date", email_data["date"])
        ]
        
        # Add header information
        pdf.set_font("Arial", size=12)
        for header, value in headers:
            if value:
                pdf.set_font("Arial", 'B', 12)
                pdf.cell(20, 10, f"{header}:", 0)
                pdf.set_font("Arial", size=12)
                # Ensure value is string and handle encoding
                pdf.cell(0, 10, str(value).encode('latin-1', 'replace').decode('latin-1'), ln=True)
        
        # Add body
        pdf.ln(10)
        pdf.set_font("Arial", size=12)
        
        # Handle body text
        body = email_data["body"]
        if body:
            # Convert body to string if it isn't already
            if not isinstance(body, str):
                body = str(body)
            
            # Replace problematic characters and encode for PDF
            body = body.encode('latin-1', 'replace').decode('latin-1')
            
            # Split body into lines and add to PDF
            lines = body.split('\n')
            for line in lines:
                pdf.multi_cell(0, 10, line)
        
        # Save PDF
        pdf_path = email_path.replace('.msg', '.pdf')
        pdf.output(pdf_path)
        
        return pdf_path
    except Exception as e:
        print(colored(f"Error converting email to PDF: {str(e)}", "red"))
        raise HTTPException(status_code=500, detail=f"Error converting email to PDF: {str(e)}")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    try:
        uploaded_files = []
        for file in files:
            # Only accept .msg files
            if not file.filename.lower().endswith('.msg'):
                print(colored(f"Skipping {file.filename} - not a .msg file", "yellow"))
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

async def read_email_content(file_path: Path) -> dict:
    """Read and parse .msg email content"""
    msg = None
    try:
        if not str(file_path).lower().endswith('.msg'):
            raise ValueError("Only .msg files are supported")

        # Parse .msg file
        msg = extract_msg.Message(str(file_path))
        
        # Get all the data we need while the file is open
        sender = str(msg.sender or "")
        to = str(msg.to or "")
        subject = str(msg.subject or "")
        date = str(msg.date or "")
        body = msg.body or ""
        
        # Convert body to string and handle encoding
        if isinstance(body, bytes):
            body = body.decode('utf-8', errors='replace')
        else:
            body = str(body)

        # Print debug info
        print(colored(f"Email content length: {len(body)}", "cyan"))
        print(colored(f"First 100 chars: {body[:100]}", "cyan"))

        return {
            "from": sender,
            "to": to,
            "subject": subject,
            "date": date,
            "body": body
        }
    except Exception as e:
        print(colored(f"Error reading email {file_path}: {str(e)}", "red"))
        raise
    finally:
        if msg is not None:
            try:
                msg.close()
            except Exception as e:
                print(colored(f"Warning: Error closing msg file: {str(e)}", "yellow"))

@app.post("/analyze")
async def analyze_emails(search_request: SearchRequest):
    try:
        # Read all .msg emails from the uploaded_emails directory
        emails_dir = Path("uploaded_emails")
        email_files = list(emails_dir.glob("*.msg"))
        
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

if __name__ == "__main__":
    # Open browser after a short delay
    asyncio.get_event_loop().run_in_executor(None, lambda: asyncio.run(asyncio.sleep(1.5)) or open_browser())
    uvicorn.run(app, host="127.0.0.1", port=8000) 