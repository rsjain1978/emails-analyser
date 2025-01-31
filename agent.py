import os
import asyncio
import json
from datetime import datetime
from pathlib import Path
from termcolor import colored
from dotenv import load_dotenv
from openai import AsyncOpenAI
import email.message
from email import encoders
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))

async def llm_call(system_prompt: str, user_prompt: str, model: str = "gpt-4o-mini") -> str:
    """Generic async function for LLM calls"""
    try:
        print(colored(f"Making LLM call with prompt: {user_prompt[:50]}...", "cyan"))
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(colored(f"Error in LLM call: {str(e)}", "red"))
        raise

async def generate_email() -> str:
    """Generate a single email using GPT-4o-mini"""
    system_prompt = """You are an email writer. Generate a realistic business email with random but realistic personal information.
    The email must have the following format:
    From: [sender email]
    To: [recipient email]
    Subject: [subject]
    
    [email body]"""
    
    user_prompt = "Generate a business email with a random topic, sender, recipient, and content. Include proper email headers."
    return await llm_call(system_prompt, user_prompt)

async def save_email_as_msg(email_content: str, index: int):
    """Save email content in EML format"""
    try:
        emails_dir = Path("emails")
        emails_dir.mkdir(exist_ok=True)
        
        # Parse email content
        lines = email_content.split('\n')
        subject = next((line for line in lines if line.startswith('Subject:')), 'No Subject').replace('Subject:', '').strip()
        from_email = next((line for line in lines if line.startswith('From:')), 'No From').replace('From:', '').strip()
        to_email = next((line for line in lines if line.startswith('To:')), 'No To').replace('To:', '').strip()
        
        # Extract body (everything after the headers)
        body_start = 0
        for i, line in enumerate(lines):
            if not line.strip():  # First empty line marks end of headers
                body_start = i + 1
                break
        body = '\n'.join(lines[body_start:])
        
        # Create email message
        msg = MIMEMultipart()
        msg['Subject'] = subject
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Date'] = email.utils.formatdate(localtime=True)
        
        # Attach body
        msg.attach(MIMEText(body, 'plain'))
        
        # Create EML file
        filename = f"email_{index}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.eml"
        filepath = emails_dir / filename
        
        # Save as EML file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(msg.as_string())
            
        print(colored(f"Saved email {index} to {filepath}", "green"))
        return str(filepath)
    except Exception as e:
        print(colored(f"Error saving email as EML: {str(e)}", "red"))
        print(colored("Falling back to saving as text file...", "yellow"))
        
        # Fallback to text file if EML creation fails
        txt_filepath = emails_dir / f"email_{index}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(txt_filepath, 'w', encoding='utf-8') as f:
            f.write(email_content)
        
        print(colored(f"Saved email {index} to {txt_filepath}", "green"))
        return str(txt_filepath)

async def analyze_email_for_pii(email_content: str) -> str:
    """Analyze email for personal information"""
    system_prompt = "You are a privacy analyst. Identify any personal information in the email."
    user_prompt = f"Analyze this email for personal information such as names, emails, phone numbers, addresses, etc:\n\n{email_content}"
    return await llm_call(system_prompt, user_prompt)

async def generate_email_summary(all_emails: list) -> str:
    """Generate a summary of all emails"""
    system_prompt = "You are an email analyst. Generate a concise summary of multiple emails."
    user_prompt = f"Generate a summary of these {len(all_emails)} emails:\n\n" + "\n---\n".join(all_emails)
    return await llm_call(system_prompt, user_prompt)

async def get_existing_emails():
    """Get existing emails from the emails folder"""
    try:
        emails_dir = Path("emails")
        if not emails_dir.exists():
            return []
        
        # Get all .eml and .txt files
        email_files = list(emails_dir.glob("*.eml")) + list(emails_dir.glob("*.txt"))
        
        # Read the contents of each file
        emails = []
        for file in email_files:
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    emails.append(f.read())
                print(colored(f"Loaded existing email from {file}", "blue"))
            except Exception as e:
                print(colored(f"Error reading {file}: {str(e)}", "red"))
        
        return emails
    except Exception as e:
        print(colored(f"Error getting existing emails: {str(e)}", "red"))
        return []

async def main():
    try:
        print(colored("Starting email generation and analysis...", "yellow"))
        
        # Check for existing emails
        existing_emails = await get_existing_emails()
        num_existing = len(existing_emails)
        num_to_generate = max(0, 10 - num_existing)
        
        print(colored(f"Found {num_existing} existing emails", "blue"))
        emails = existing_emails.copy()
        email_paths = []
        
        # Generate additional emails if needed
        if num_to_generate > 0:
            print(colored(f"Generating {num_to_generate} new emails...", "yellow"))
            for i in range(num_to_generate):
                print(colored(f"Generating email {i+1}/{num_to_generate}...", "blue"))
                email_content = await generate_email()
                emails.append(email_content)
                
                # Save email
                email_path = await save_email_as_msg(email_content, num_existing + i + 1)
                email_paths.append(email_path)
        else:
            print(colored("Using existing emails, no new generation needed", "green"))
        
        # Parallel analysis tasks
        print(colored("Starting parallel analysis of emails...", "yellow"))
        analysis_tasks = [analyze_email_for_pii(email) for email in emails]
        analysis_tasks.append(generate_email_summary(emails))
        
        # Wait for all analysis tasks to complete
        results = await asyncio.gather(*analysis_tasks)
        
        # Separate PII analysis results and summary
        pii_results = results[:-1]
        summary = results[-1]
        
        # Print results
        print(colored("\nPII Analysis Results:", "green"))
        for i, pii_result in enumerate(pii_results):
            print(colored(f"\nEmail {i+1} PII Analysis:", "cyan"))
            print(pii_result)
            
        print(colored("\nEmail Summary:", "green"))
        print(summary)
        
    except Exception as e:
        print(colored(f"Error in main execution: {str(e)}", "red"))
        raise

if __name__ == "__main__":
    asyncio.run(main()) 