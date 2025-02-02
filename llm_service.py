from openai import AsyncOpenAI
import os
import json
from typing import List, Dict
from termcolor import colored
from prompts import EMAIL_ANALYSIS_SYSTEM_PROMPT, EMAIL_SUMMARY_SYSTEM_PROMPT, EMAIL_ANALYSIS_USER_PROMPT_TEMPLATE

from dotenv import load_dotenv  
load_dotenv()

class LLMService:
    def __init__(self):
        self.client = AsyncOpenAI()
        self.MODEL = "gpt-4o"  # Using the specified model

    def extract_email_content(self, email_raw: str) -> Dict[str, str]:
        """Extract subject and body from email, removing headers"""
        try:
            # Split email into headers and body
            parts = email_raw.split('\n\n', 1)
            headers = parts[0]
            body = parts[1] if len(parts) > 1 else ""

            # Extract subject from headers
            subject = ""
            for line in headers.split('\n'):
                if line.lower().startswith('subject:'):
                    subject = line[8:].strip()
                    break

            return {
                "subject": subject,
                "body": body.strip()
            }
        except Exception as e:
            print(colored(f"Error extracting email content: {str(e)}", "red"))
            return {
                "subject": "",
                "body": email_raw  # Fallback to using entire content
            }

    async def analyze_email_content(self, email_content: str, search_terms: List[str]) -> dict:
        """Analyze email content for semantic matches with search terms"""
        try:
            # Format the user prompt with the search terms and email content
            user_prompt = EMAIL_ANALYSIS_USER_PROMPT_TEMPLATE.format(
                search_terms=', '.join(search_terms),
                email_content=email_content
            )

            completion = await self.client.chat.completions.create(
                model=self.MODEL,
                messages=[
                    {"role": "system", "content": EMAIL_ANALYSIS_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"}
            )

            return completion.choices[0].message.content

        except Exception as e:
            print(colored(f"Error in analyze_email_content: {str(e)}", "red"))
            raise

    async def generate_summary(self, all_emails: List[str], search_terms: List[str]) -> str:
        """Generate a summary of all emails focusing on semantic matches to search terms"""
        try:
            system_prompt = EMAIL_SUMMARY_SYSTEM_PROMPT.format(terms=', '.join(search_terms))
            
            # Process emails to extract subjects and bodies
            processed_emails = [self.extract_email_content(email) for email in all_emails]
            formatted_emails = [
                f"Subject: {email['subject']}\n\nBody:\n{email['body']}"
                for email in processed_emails
            ]
            
            user_prompt = f"Generate a semantic analysis summary for these emails:\n\n" + "\n---\n".join(formatted_emails)
            
            completion = await self.client.chat.completions.create(
                model=self.MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            return completion.choices[0].message.content.strip()
            
        except Exception as e:
            print(colored(f"Error in LLM summary generation: {str(e)}", "red"))
            raise 