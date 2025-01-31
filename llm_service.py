from openai import AsyncOpenAI
import os
import re
from typing import List, Dict
from termcolor import colored

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

    async def analyze_email_content(self, email_content: str, search_terms: List[str]) -> Dict:
        """
        Analyze email content for semantic references to search terms
        Returns a dictionary with search results
        """
        try:
            # Extract subject and body
            email_parts = self.extract_email_content(email_content)
            
            system_prompt = f"""You are an expert email analyst focusing on semantic analysis.
            Analyze the email subject and body for any semantic references or conceptual mentions related to these terms: {', '.join(search_terms)}

            Rules:
            - ONLY analyze the email subject and body text
            - IGNORE all email addresses (From:, To:, CC:, etc.)
            - Look for semantic matches, not just exact keywords
            - Consider synonyms, related concepts, and contextual references
            - Include both direct and indirect references that are semantically related
            - For each found reference, provide:
                * The exact text from the email containing the reference
                * Brief explanation of how it relates to the search term
            
            Return ONLY in this JSON format:
            {{
                "original_email": "full email content",
                "subject": "email subject",
                "terms_found": ["term1", "term2"],
                "semantic_matches": {{
                    "term1": [
                        {{
                            "text": "relevant text from email",
                            "explanation": "how this relates to term1",
                            "location": "subject|body"
                        }}
                    ],
                    "term2": [
                        {{
                            "text": "relevant text from email",
                            "explanation": "how this relates to term2",
                            "location": "subject|body"
                        }}
                    ]
                }}
            }}"""
            
            user_prompt = f"""Analyze this email for semantic references to the specified terms:

Subject: {email_parts['subject']}

Body:
{email_parts['body']}"""
            
            completion = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={ "type": "json_object" }
            )
            
            return completion.choices[0].message.content
            
        except Exception as e:
            print(colored(f"Error in LLM service: {str(e)}", "red"))
            raise

    async def generate_summary(self, all_emails: List[str], search_terms: List[str]) -> str:
        """Generate a summary of all emails focusing on semantic matches to search terms"""
        try:
            system_prompt = f"""You are an expert email analyst. Generate a comprehensive summary of the semantic analysis results.
            Focus on these terms: {', '.join(search_terms)}

            Rules:
            - Focus ONLY on email subjects and body content
            - IGNORE all email addresses and headers
            
            Analyze and summarize:
            - Key semantic patterns and relationships between terms
            - Direct and indirect references to the search terms
            - Important contextual relationships
            - Notable insights from semantic analysis
            - Patterns in how terms appear in subjects vs body content
            
            Format your response in clear HTML with:
            - <h3> for main sections
            - <h4> for subsections
            - <p> for content
            - <ul>/<li> for lists
            - Use appropriate semantic HTML elements"""
            
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
            
            return completion.choices[0].message.content
            
        except Exception as e:
            print(colored(f"Error in LLM summary generation: {str(e)}", "red"))
            raise 