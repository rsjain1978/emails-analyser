from openai import AsyncOpenAI
import os
import json
from typing import List, Dict
from termcolor import colored
from prompts import EMAIL_ANALYSIS_SYSTEM_PROMPT, EMAIL_SUMMARY_SYSTEM_PROMPT

from dotenv import load_dotenv  
load_dotenv()

class LLMService:
    def __init__(self):
        self.client = AsyncOpenAI()
        self.model = "gpt-4o-mini"  # Default model

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

    async def analyze_email_content(self, email_content: str, search_terms: List[str]) -> str:
        """Analyze email content for semantic references to search terms"""
        try:
            # Extract subject and body
            email_parts = self.extract_email_content(email_content)
            
            system_prompt = EMAIL_ANALYSIS_SYSTEM_PROMPT.format(terms=', '.join(search_terms))
            user_prompt = f"""Analyze this email for semantic references to the specified terms:

Subject: {email_parts['subject']}

Body:
{email_parts['body']}"""

            # Print prompts for debugging
            print(colored("\nSystem Prompt:", "yellow"))
            print(colored(system_prompt, "yellow"))
            print(colored("\nUser Prompt:", "yellow"))
            print(colored(user_prompt, "yellow"))
            
            completion = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={ "type": "json_object" }
            )
            
            # Get the response content and ensure it's valid JSON
            response_content = completion.choices[0].message.content.strip()
            
            # Validate JSON response
            try:
                json_response = json.loads(response_content)
                return json.dumps(json_response)  # Return properly formatted JSON string
            except json.JSONDecodeError as e:
                print(colored(f"Invalid JSON response from LLM: {response_content}", "red"))
                # Return a valid fallback JSON response
                fallback_response = {
                    "original_email": email_content,
                    "subject": email_parts["subject"],
                    "terms_found": [],
                    "semantic_matches": {}
                }
                return json.dumps(fallback_response)
            
        except Exception as e:
            print(colored(f"Error in LLM service: {str(e)}", "red"))
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
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            return completion.choices[0].message.content.strip()
            
        except Exception as e:
            print(colored(f"Error in LLM summary generation: {str(e)}", "red"))
            raise 