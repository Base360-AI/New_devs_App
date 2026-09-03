import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Cc, Content, Attachment, FileContent, FileName, FileType, Disposition, Personalization
from typing import Optional, List
import logging
import os
import base64
from ..config import settings

logger = logging.getLogger(__name__)

class EmailClient:
    def __init__(self):
        try:
            if not hasattr(settings, 'sendgrid_api_key') or not settings.sendgrid_api_key:
                raise ValueError("SendGrid API key not configured")
            if not hasattr(settings, 'sendgrid_from_email') or not settings.sendgrid_from_email:
                raise ValueError("SendGrid from email not configured")
                
            self.sg = sendgrid.SendGridAPIClient(api_key=settings.sendgrid_api_key)
            self.from_email = Email(settings.sendgrid_from_email, "The Flex")
            logger.info("EmailClient initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize EmailClient: {e}")
            raise
    
    async def send_email(
        self, 
        to_email: str, 
        subject: str, 
        html_content: str, 
        text_content: str,
        cc_email: Optional[str] = None
    ) -> bool:
        """Send email via SendGrid with support for multiple CC recipients"""
        try:
            logger.info("Attempting to send email")
            
            # Support multiple TO emails separated by commas
            to_emails = [email.strip() for email in to_email.split(',') if email.strip()]
            if not to_emails:
                logger.error("No valid TO email addresses provided")
                return False
            
            # Prepare CC emails if provided
            cc_emails = []
            if cc_email and cc_email.strip():
                cc_emails = [email.strip() for email in cc_email.split(',') if email.strip()]
                logger.info(f"CC recipients: {', '.join(cc_emails)}")
            
            # Create Mail object using Personalization for proper recipient handling
            mail = Mail(
                from_email=self.from_email,
                subject=subject,
                html_content=html_content
            )
            
            # Add plain text content
            mail.add_content(Content("text/plain", text_content))
            
            # Create personalization object for recipients
            personalization = Personalization()
            
            # Add TO recipients
            for to_recipient in to_emails:
                personalization.add_to(To(to_recipient))
                logger.info(f"Added TO recipient: {to_recipient}")
            
            # Add CC recipients
            for cc_recipient in cc_emails:
                personalization.add_cc(Cc(cc_recipient))
                logger.info(f"Added CC recipient: {cc_recipient}")
            
            # Add personalization to mail
            mail.add_personalization(personalization)
            
            response = self.sg.client.mail.send.post(request_body=mail.get())
            
            if response.status_code in [200, 201, 202]:
                logger.info("Email sent successfully")
                if cc_emails:
                    logger.info(f"CC sent to: {', '.join(cc_emails)}")
                return True
            else:
                logger.error(f"Failed to send email: {response.status_code} - {response.body}")
                return False
                
        except Exception as e:
            logger.error("Email delivery failed: %s", type(e).__name__)
            return False
                
    async def send_email_with_attachment(self, to_email: str, subject: str, html_content: str, 
                        attachment_path: str = None, attachment_name: str = None, cc_email: Optional[str] = None):
        """Send email with optional attachment and CC support"""
        try:
            # Support multiple TO emails separated by commas
            to_emails = [email.strip() for email in to_email.split(',') if email.strip()]
            if not to_emails:
                logger.error("No valid TO email addresses provided")
                return False
            
            # Prepare CC emails if provided
            cc_emails = []
            if cc_email and cc_email.strip():
                cc_emails = [email.strip() for email in cc_email.split(',') if email.strip()]
                logger.info(f"CC recipients: {', '.join(cc_emails)}")
            
            # Create Mail object using Personalization for proper recipient handling
            message = Mail(
                from_email=self.from_email,
                subject=subject,
                html_content=html_content
            )
            
            # Create personalization object for recipients
            personalization = Personalization()
            
            # Add TO recipients
            for to_recipient in to_emails:
                personalization.add_to(To(to_recipient))
                logger.info(f"Added TO recipient: {to_recipient}")
            
            # Add CC recipients
            for cc_recipient in cc_emails:
                personalization.add_cc(Cc(cc_recipient))
                logger.info(f"Added CC recipient: {cc_recipient}")
            
            # Add personalization to message
            message.add_personalization(personalization)
            
            # Add attachment if provided
            if attachment_path and os.path.exists(attachment_path):
                with open(attachment_path, 'rb') as f:
                    data = f.read()
                    encoded_file = base64.b64encode(data).decode()
                
                attachment = Attachment(
                    FileContent(encoded_file),
                    FileName(attachment_name or os.path.basename(attachment_path)),
                    FileType('application/pdf'),
                    Disposition('attachment')
                )
                message.attachment = attachment
            
            response = self.sg.send(message)
            return response.status_code == 202
            
        except Exception as e:
            logger.error(f"Error sending email with attachment: {e}")
            raise e

# Global email client instance
try:
    email_client = EmailClient()
except Exception as e:
    logger.error(f"Failed to create global email client: {e}")
    email_client = None
