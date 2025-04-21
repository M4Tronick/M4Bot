"""
M4Bot Email Service

Questo modulo gestisce l'invio di email per varie funzionalità dell'applicazione.
Supporta email di recupero password, notifiche, conferme e inviti.
"""

import os
import logging
import smtplib
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from typing import Dict, List, Union, Optional, Any
from datetime import datetime, timedelta

# Configurazione logging
logger = logging.getLogger("m4bot.email")

class EmailService:
    """Servizio di invio email per M4Bot."""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Inizializza il servizio email
        
        Args:
            config: Configurazione SMTP (opzionale, altrimenti usa variabili d'ambiente)
        """
        self.config = config or {}
        self.smtp_host = self.config.get('smtp_host', os.getenv('SMTP_HOST', 'smtp.gmail.com'))
        self.smtp_port = int(self.config.get('smtp_port', os.getenv('SMTP_PORT', '587')))
        self.smtp_user = self.config.get('smtp_user', os.getenv('SMTP_USER', ''))
        self.smtp_password = self.config.get('smtp_password', os.getenv('SMTP_PASSWORD', ''))
        self.from_email = self.config.get('from_email', os.getenv('FROM_EMAIL', 'noreply@m4bot.it'))
        self.from_name = self.config.get('from_name', os.getenv('FROM_NAME', 'M4Bot'))
        
        # Verifica credenziali
        self._check_credentials()
    
    def _check_credentials(self):
        """Verifica che le credenziali SMTP siano configurate."""
        if not all([self.smtp_host, self.smtp_port, self.smtp_user, self.smtp_password]):
            logger.warning("Credenziali SMTP non completamente configurate. L'invio di email potrebbe fallire.")
    
    async def send_email(self, 
                        to_email: str, 
                        subject: str, 
                        text_content: str, 
                        html_content: Optional[str] = None, 
                        cc: Optional[List[str]] = None,
                        bcc: Optional[List[str]] = None,
                        attachments: Optional[List[Dict[str, Any]]] = None,
                        images: Optional[List[Dict[str, Any]]] = None) -> bool:
        """
        Invia un'email.
        
        Args:
            to_email: Indirizzo email del destinatario
            subject: Oggetto dell'email
            text_content: Contenuto in testo semplice
            html_content: Contenuto HTML (opzionale)
            cc: Lista di destinatari in copia (opzionale)
            bcc: Lista di destinatari in copia nascosta (opzionale)
            attachments: Lista di allegati [{'filename': 'nome.txt', 'data': b'dati'}] (opzionale)
            images: Lista di immagini da incorporare [{'cid': 'id', 'data': b'dati', 'filename': 'img.jpg'}] (opzionale)
            
        Returns:
            bool: True se l'invio è avvenuto con successo, False altrimenti
        """
        try:
            # Crea il messaggio
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to_email
            
            if cc:
                msg['Cc'] = ", ".join(cc)
            
            if bcc:
                msg['Bcc'] = ", ".join(bcc)
            
            # Aggiungi corpo testo semplice
            msg.attach(MIMEText(text_content, 'plain'))
            
            # Aggiungi corpo HTML se fornito
            if html_content:
                msg.attach(MIMEText(html_content, 'html'))
            
            # Aggiungi immagini incorporate
            if images:
                for img in images:
                    image = MIMEImage(img['data'])
                    image.add_header('Content-ID', f"<{img['cid']}>")
                    image.add_header('Content-Disposition', 'inline', filename=img['filename'])
                    msg.attach(image)
            
            # Invia l'email in un thread separato
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._send_email_sync, msg, to_email)
            
            return True
        except Exception as e:
            logger.error(f"Errore nell'invio dell'email a {to_email}: {e}")
            return False
    
    def _send_email_sync(self, msg, to_email):
        """Funzione sincrona per l'invio email (eseguita in un thread separato)."""
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            server.send_message(msg)
            logger.info(f"Email inviata con successo a {to_email}")
    
    async def send_password_reset(self, to_email: str, username: str, reset_link: str) -> bool:
        """
        Invia un'email di recupero password.
        
        Args:
            to_email: Indirizzo email del destinatario
            username: Nome utente
            reset_link: Link per il reset della password
            
        Returns:
            bool: True se l'invio è avvenuto con successo, False altrimenti
        """
        subject = "Recupero Password M4Bot"
        
        text_content = f"""
        Ciao {username},
        
        Hai richiesto di reimpostare la tua password su M4Bot.
        
        Per completare il processo, clicca sul seguente link:
        {reset_link}
        
        Questo link scadrà tra 2 ore.
        
        Se non hai richiesto tu di reimpostare la password, ignora questa email.
        
        Grazie,
        Il team di M4Bot
        """
        
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(to right, #4a86e8, #7367f0); color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
                .content {{ background-color: #f8f9fa; padding: 30px; border-radius: 0 0 5px 5px; }}
                .button {{ display: inline-block; background: linear-gradient(to right, #4a86e8, #7367f0); color: white; 
                          padding: 12px 25px; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
                .footer {{ font-size: 12px; color: #777; text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Recupero Password</h1>
                </div>
                <div class="content">
                    <p>Ciao <strong>{username}</strong>,</p>
                    <p>Hai richiesto di reimpostare la tua password su M4Bot.</p>
                    <p>Per completare il processo, clicca sul seguente pulsante:</p>
                    <p style="text-align: center;">
                        <a href="{reset_link}" class="button">Reimposta Password</a>
                    </p>
                    <p>Oppure copia e incolla il seguente link nel tuo browser:</p>
                    <p style="word-break: break-all; font-size: 14px;">{reset_link}</p>
                    <p>Questo link scadrà tra <strong>2 ore</strong>.</p>
                    <p>Se non hai richiesto tu di reimpostare la password, puoi ignorare questa email.</p>
                </div>
                <div class="footer">
                    <p>&copy; {datetime.now().year} M4Bot - Tutti i diritti riservati</p>
                    <p>Questa è un'email automatica, si prega di non rispondere.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return await self.send_email(to_email, subject, text_content, html_content)
    
    async def send_welcome_email(self, to_email: str, username: str) -> bool:
        """
        Invia un'email di benvenuto a un nuovo utente.
        
        Args:
            to_email: Indirizzo email del destinatario
            username: Nome utente
            
        Returns:
            bool: True se l'invio è avvenuto con successo, False altrimenti
        """
        subject = "Benvenuto su M4Bot!"
        
        text_content = f"""
        Ciao {username},
        
        Benvenuto su M4Bot! Siamo felici di averti con noi.
        
        Il tuo account è stato creato con successo. Puoi accedere alla tua dashboard personale in qualsiasi momento.
        
        Se hai domande o suggerimenti, non esitare a contattarci.
        
        Grazie,
        Il team di M4Bot
        """
        
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(to right, #4a86e8, #7367f0); color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
                .content {{ background-color: #f8f9fa; padding: 30px; border-radius: 0 0 5px 5px; }}
                .footer {{ font-size: 12px; color: #777; text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Benvenuto su M4Bot!</h1>
                </div>
                <div class="content">
                    <p>Ciao <strong>{username}</strong>,</p>
                    <p>Benvenuto su M4Bot! Siamo felici di averti con noi.</p>
                    <p>Il tuo account è stato creato con successo. Puoi accedere alla tua dashboard personale in qualsiasi momento.</p>
                    <p>Se hai domande o suggerimenti, non esitare a contattarci.</p>
                </div>
                <div class="footer">
                    <p>&copy; {datetime.now().year} M4Bot - Tutti i diritti riservati</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return await self.send_email(to_email, subject, text_content, html_content)
    
    async def send_security_notification(self, to_email: str, username: str, activity: str, ip_address: str, location: str, device: str, time: datetime) -> bool:
        """
        Invia una notifica di sicurezza all'utente.
        
        Args:
            to_email: Indirizzo email del destinatario
            username: Nome utente
            activity: Tipo di attività (login, reset password, ecc.)
            ip_address: Indirizzo IP
            location: Posizione approssimativa
            device: Dispositivo utilizzato
            time: Data e ora dell'attività
            
        Returns:
            bool: True se l'invio è avvenuto con successo, False altrimenti
        """
        subject = "Avviso di Sicurezza M4Bot"
        
        formatted_time = time.strftime("%d/%m/%Y %H:%M:%S")
        
        text_content = f"""
        Ciao {username},
        
        Abbiamo rilevato una nuova attività sul tuo account M4Bot.
        
        Dettagli:
        - Attività: {activity}
        - Data e ora: {formatted_time}
        - Indirizzo IP: {ip_address}
        - Posizione: {location}
        - Dispositivo: {device}
        
        Se non sei stato tu a effettuare questa operazione, ti consigliamo di cambiare immediatamente la password.
        
        Grazie,
        Il team di M4Bot
        """
        
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(to right, #4a86e8, #7367f0); color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
                .content {{ background-color: #f8f9fa; padding: 30px; border-radius: 0 0 5px 5px; }}
                .activity-details {{ background-color: white; padding: 15px; border-radius: 5px; margin: 15px 0; }}
                .detail {{ margin-bottom: 10px; }}
                .detail strong {{ display: inline-block; width: 100px; }}
                .warning {{ color: #e74c3c; font-weight: bold; }}
                .button {{ display: inline-block; background: linear-gradient(to right, #4a86e8, #7367f0); color: white; 
                          padding: 12px 25px; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
                .footer {{ font-size: 12px; color: #777; text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Avviso di Sicurezza</h1>
                </div>
                <div class="content">
                    <p>Ciao <strong>{username}</strong>,</p>
                    <p>Abbiamo rilevato una nuova attività sul tuo account M4Bot.</p>
                    
                    <div class="activity-details">
                        <div class="detail"><strong>Attività:</strong> {activity}</div>
                        <div class="detail"><strong>Data e ora:</strong> {formatted_time}</div>
                        <div class="detail"><strong>IP:</strong> {ip_address}</div>
                        <div class="detail"><strong>Posizione:</strong> {location}</div>
                        <div class="detail"><strong>Dispositivo:</strong> {device}</div>
                    </div>
                    
                    <p class="warning">Se non sei stato tu a effettuare questa operazione, ti consigliamo di cambiare immediatamente la password.</p>
                    
                    <p style="text-align: center;">
                        <a href="https://m4bot.it/reset_password" class="button">Cambia Password</a>
                    </p>
                </div>
                <div class="footer">
                    <p>&copy; {datetime.now().year} M4Bot - Tutti i diritti riservati</p>
                    <p>Questa è un'email automatica, si prega di non rispondere.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return await self.send_email(to_email, subject, text_content, html_content)


# Istanza globale del servizio email
_email_service = None

async def get_email_service(config: Dict[str, Any] = None) -> EmailService:
    """
    Ottiene l'istanza del servizio email, creandola se necessario.
    
    Args:
        config: Configurazione SMTP (opzionale)
        
    Returns:
        EmailService: Istanza del servizio email
    """
    global _email_service
    
    if _email_service is None:
        _email_service = EmailService(config)
    
    return _email_service 