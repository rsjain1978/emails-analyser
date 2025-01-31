import os
import asyncio
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

async def generate_email(theme: str) -> str:
    """Generate a single email using GPT-4o-mini with a specific theme"""
    system_prompt = """You are an email writer. Generate a realistic email in plain text format.
    The email should be in English and follow this exact format:

    From: [realistic email address]
    To: [realistic email address]
    Subject: [clear subject related to the theme]
   
    Keep the content natural and appropriate. Do not include any special characters or encoding.
    The email content should be focused on the specified theme."""
    
    user_prompt = f"Generate a email about the theme: '{theme}'. Include realistic sender, recipient, and make it look like a real email exchange. The content should be specifically about {theme}."
    return await llm_call(system_prompt, user_prompt)

async def save_email_as_msg(email_content: str, index: int):
    """Save email content in EML format"""
    try:
        emails_dir = Path("emails")
        emails_dir.mkdir(exist_ok=True)
        
        # Parse email content
        lines = email_content.split('\n')
        headers = {}
        body_lines = []
        in_headers = True
        
        for line in lines:
            if in_headers:
                if not line.strip():  # Empty line marks end of headers
                    in_headers = False
                    continue
                if ':' in line:
                    key, value = line.split(':', 1)
                    headers[key.strip()] = value.strip()
            else:
                body_lines.append(line)
        
        body = '\n'.join(body_lines)
        
        # Create email message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = headers.get('Subject', 'No Subject')
        msg['From'] = headers.get('From', 'no-reply@example.com')
        msg['To'] = headers.get('To', 'recipient@example.com')
        msg['Date'] = email.utils.formatdate(localtime=True)
        
        # Attach body as plain text
        text_part = MIMEText(body, 'plain', 'utf-8')
        msg.attach(text_part)
        
        # Create EML file
        filename = f"email_{index}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.eml"
        filepath = emails_dir / filename
        
        # Save as EML file with proper encoding
        with open(filepath, 'w', encoding='utf-8') as f:
            # Write headers
            for key, value in headers.items():
                f.write(f"{key}: {value}\n")
            f.write("\n")  # Empty line between headers and body
            f.write(body)  # Write the body directly
            
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

async def generate_emails(num_emails: int = None):
    """Generate multiple emails"""
    try:
        if num_emails is None:
            # Ask user for number of emails to generate
            while True:
                try:
                    num_emails = int(input(colored("How many emails would you like to generate? ", "yellow")))
                    if num_emails > 0:
                        break
                    print(colored("Please enter a positive number.", "red"))
                except ValueError:
                    print(colored("Please enter a valid number.", "red"))
        
        # Get theme from user
        theme = input(colored("Please enter the theme for the emails (e.g., 'project updates', 'sales inquiries', 'team collaboration'): ", "yellow")).strip()
        while not theme:
            print(colored("Theme cannot be empty.", "red"))
            theme = input(colored("Please enter the theme for the emails: ", "yellow")).strip()

        print(colored(f"\nStarting generation of {num_emails} emails with theme: '{theme}'...", "blue"))
        
        emails = []
        email_paths = []
        
        for i in range(num_emails):
            print(colored(f"\nGenerating email {i+1}/{num_emails}...", "blue"))
            email_content = await generate_email(theme)
            emails.append(email_content)
            
            # Save email
            email_path = await save_email_as_msg(email_content, i+1)
            email_paths.append(email_path)
            
            # Show progress
            print(colored(f"Progress: {i+1}/{num_emails} emails generated", "green"))
            
        print(colored(f"\nSuccessfully generated {num_emails} themed emails!", "green"))
        return emails, email_paths
    except Exception as e:
        print(colored(f"Error generating emails: {str(e)}", "red"))
        raise

if __name__ == "__main__":
    try:
        print(colored("\n=== Themed Email Generator ===", "blue"))
        print(colored("This script will generate synthetic business emails using AI based on your chosen theme.\n", "blue"))
        asyncio.run(generate_emails())
    except KeyboardInterrupt:
        print(colored("\nOperation cancelled by user.", "yellow"))
    except Exception as e:
        print(colored(f"\nAn error occurred: {str(e)}", "red"))
    finally:
        print(colored("\nEmail generation complete.", "green")) 