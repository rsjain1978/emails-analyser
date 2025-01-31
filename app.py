import os
import asyncio
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
import uvicorn
import webbrowser
from email_generator import generate_emails
from typing import List
import aiofiles
from termcolor import colored
from pydantic import BaseModel
from llm_service import LLMService
from csv_handler import CSVHandler
import shutil
from fpdf import FPDF
import email
import mimetypes

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
csv_handler = CSVHandler()

class SearchRequest(BaseModel):
    search_terms: List[str]

async def process_batch(emails_batch: List[str], search_terms: List[str]) -> List[dict]:
    """Process a batch of emails with concurrent API calls"""
    try:
        print(colored(f"Starting analysis for {len(emails_batch)} emails...", "cyan"))
        tasks = [llm_service.analyze_email_content(email, search_terms) for email in emails_batch]
        
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
            batch = [email["content"] for email in emails[i:i + BATCH_SIZE]]
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

@app.post("/analyze")
async def analyze_emails(search_request: SearchRequest):
    try:
        # Read all emails from the uploaded_emails directory
        emails_dir = Path("uploaded_emails")
        email_files = list(emails_dir.glob("*.eml")) + list(emails_dir.glob("*.txt"))
        
        emails = []
        for file in email_files:
            async with aiofiles.open(file, mode='r', encoding='utf-8') as f:
                content = await f.read()
                email_message = email.message_from_string(content)
                emails.append({
                    "filename": file.name,
                    "subject": email_message["subject"],
                    "content": content
                })

        print(colored(f"Found {len(emails)} emails to analyze", "blue"))
        
        # Process email analysis in batches
        print(colored("Starting email analysis in batches...", "blue"))
        analysis_results = await process_emails_in_batches(emails, search_request.search_terms)
        
        # Generate CSV report
        print(colored("Generating CSV report...", "blue"))
        csv_path = await csv_handler.create_analysis_csv(
            [email["content"] for email in emails],
            [result["analysis"] for result in analysis_results],
            search_request.search_terms
        )
        
        # Generate overall summary
        print(colored("Generating overall summary...", "blue"))
        summary = await llm_service.generate_summary([email["content"] for email in emails], search_request.search_terms)
        
        print(colored("Analysis complete!", "green"))
        
        return {
            "status": "success",
            "analysis_results": analysis_results,
            "summary": summary,
            "num_emails": len(emails),
            "csv_path": csv_path
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
            
        async with aiofiles.open(email_path, mode='r', encoding='utf-8') as f:
            content = await f.read()
            email_message = email.message_from_string(content)
            
            return {
                "from": email_message["from"],
                "to": email_message["to"],
                "subject": email_message["subject"],
                "date": email_message["date"],
                "body": email_message.get_payload()
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def open_browser():
    webbrowser.open("http://localhost:8000")

if __name__ == "__main__":
    # Open browser after a short delay
    asyncio.get_event_loop().run_in_executor(None, lambda: asyncio.run(asyncio.sleep(1.5)) or open_browser())
    uvicorn.run(app, host="127.0.0.1", port=8000) 