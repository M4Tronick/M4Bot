@echo off
echo =======================================
echo      M4Bot - Fix Installation Script
echo =======================================
echo.

REM Verifica se lo script è eseguito come amministratore
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Errore: Questo script deve essere eseguito come amministratore!
    echo Chiudi questa finestra e riavvia lo script come amministratore.
    pause
    exit /b 1
)

echo [INFO] Verifico e creo le directory necessarie...
if not exist "scripts" mkdir scripts
if not exist "modules" mkdir modules
if not exist "modules\security" mkdir modules\security
if not exist "modules\stability" mkdir modules\stability
if not exist "modules\security\waf" mkdir modules\security\waf
if not exist "modules\security\advanced" mkdir modules\security\advanced
if not exist "logs" mkdir logs

echo [INFO] Creo lo script check_services.sh nella directory scripts...
echo #!/bin/bash > scripts\check_services.sh
echo # Script per verificare i servizi di M4Bot >> scripts\check_services.sh
echo. >> scripts\check_services.sh
echo # Colori per output >> scripts\check_services.sh
echo RED='\033[0;31m' >> scripts\check_services.sh
echo GREEN='\033[0;32m' >> scripts\check_services.sh
echo YELLOW='\033[0;33m' >> scripts\check_services.sh
echo BLUE='\033[0;34m' >> scripts\check_services.sh
echo NC='\033[0m' # No Color >> scripts\check_services.sh
echo. >> scripts\check_services.sh
echo # Funzioni di utilità >> scripts\check_services.sh
echo print_message^(^) ^{ >> scripts\check_services.sh
echo     echo -e "${BLUE}[M4Bot]${NC} $1" >> scripts\check_services.sh
echo ^} >> scripts\check_services.sh
echo. >> scripts\check_services.sh
echo print_error^(^) ^{ >> scripts\check_services.sh
echo     echo -e "${RED}[ERRORE]${NC} $1" >> scripts\check_services.sh
echo ^} >> scripts\check_services.sh
echo. >> scripts\check_services.sh
echo print_success^(^) ^{ >> scripts\check_services.sh
echo     echo -e "${GREEN}[SUCCESSO]${NC} $1" >> scripts\check_services.sh
echo ^} >> scripts\check_services.sh
echo. >> scripts\check_services.sh
echo print_warning^(^) ^{ >> scripts\check_services.sh
echo     echo -e "${YELLOW}[AVVISO]${NC} $1" >> scripts\check_services.sh
echo ^} >> scripts\check_services.sh

echo [INFO] Creo lo script start.sh nella directory scripts...
echo #!/bin/bash > scripts\start.sh
echo # Script per avviare i servizi M4Bot >> scripts\start.sh
echo. >> scripts\start.sh
echo # Colori per output >> scripts\start.sh
echo RED='\033[0;31m' >> scripts\start.sh
echo GREEN='\033[0;32m' >> scripts\start.sh
echo YELLOW='\033[0;33m' >> scripts\start.sh
echo BLUE='\033[0;34m' >> scripts\start.sh
echo NC='\033[0m' # No Color >> scripts\start.sh
echo. >> scripts\start.sh
echo echo -e "${BLUE}[M4Bot]${NC} Avvio di M4Bot..." >> scripts\start.sh
echo. >> scripts\start.sh
echo # Verifica che la directory dei log esista >> scripts\start.sh
echo if [ ! -d "logs" ]; then >> scripts\start.sh
echo     echo -e "${YELLOW}[AVVISO]${NC} La directory dei log non esiste, creazione in corso..." >> scripts\start.sh
echo     mkdir -p logs >> scripts\start.sh
echo     echo -e "${GREEN}[SUCCESSO]${NC} Directory dei log creata" >> scripts\start.sh
echo fi >> scripts\start.sh
echo. >> scripts\start.sh
echo echo -e "${BLUE}[M4Bot]${NC} Controllo dei servizi..." >> scripts\start.sh
echo. >> scripts\start.sh
echo # Verifica PostgreSQL >> scripts\start.sh
echo if command -v pg_isready &> /dev/null; then >> scripts\start.sh
echo     if pg_isready -q; then >> scripts\start.sh
echo         echo -e "${GREEN}[SUCCESSO]${NC} PostgreSQL è in esecuzione" >> scripts\start.sh
echo     else >> scripts\start.sh
echo         echo -e "${YELLOW}[AVVISO]${NC} PostgreSQL non è in esecuzione, tentativo di avvio..." >> scripts\start.sh
echo         systemctl start postgresql >> scripts\start.sh
echo         if [ $? -ne 0 ]; then >> scripts\start.sh
echo             echo -e "${RED}[ERRORE]${NC} Impossibile avviare PostgreSQL" >> scripts\start.sh
echo         fi >> scripts\start.sh
echo     fi >> scripts\start.sh
echo else >> scripts\start.sh
echo     echo -e "${YELLOW}[AVVISO]${NC} PostgreSQL non è installato" >> scripts\start.sh
echo fi >> scripts\start.sh

echo [INFO] Creo i file base del modulo WAF...
echo # Web Application Firewall module for M4Bot > modules\security\waf\__init__.py
echo. >> modules\security\waf\__init__.py
echo import logging >> modules\security\waf\__init__.py
echo from datetime import datetime >> modules\security\waf\__init__.py
echo. >> modules\security\waf\__init__.py
echo logger = logging.getLogger('m4bot.security.waf') >> modules\security\waf\__init__.py
echo. >> modules\security\waf\__init__.py
echo class WAF: >> modules\security\waf\__init__.py
echo     def __init__(self, app=None): >> modules\security\waf\__init__.py
echo         self.app = app >> modules\security\waf\__init__.py
echo         logger.info("WAF initialized at %%s", datetime.now()) >> modules\security\waf\__init__.py
echo. >> modules\security\waf\__init__.py
echo     def init_app(self, app): >> modules\security\waf\__init__.py
echo         self.app = app >> modules\security\waf\__init__.py
echo         logger.info("WAF attached to app at %%s", datetime.now()) >> modules\security\waf\__init__.py

echo [INFO] Creo il file base del modulo di sicurezza avanzata...
echo # Advanced Security module for M4Bot > modules\security\advanced\__init__.py
echo. >> modules\security\advanced\__init__.py
echo import logging >> modules\security\advanced\__init__.py
echo from datetime import datetime >> modules\security\advanced\__init__.py
echo. >> modules\security\advanced\__init__.py
echo logger = logging.getLogger('m4bot.security.advanced') >> modules\security\advanced\__init__.py
echo. >> modules\security\advanced\__init__.py
echo class AdvancedSecurity: >> modules\security\advanced\__init__.py
echo     def __init__(self): >> modules\security\advanced\__init__.py
echo         logger.info("Advanced Security module initialized at %%s", datetime.now()) >> modules\security\advanced\__init__.py
echo. >> modules\security\advanced\__init__.py
echo     def start_monitoring(self): >> modules\security\advanced\__init__.py
echo         logger.info("Advanced Security monitoring started at %%s", datetime.now()) >> modules\security\advanced\__init__.py
echo. >> modules\security\advanced\__init__.py
echo     def stop_monitoring(self): >> modules\security\advanced\__init__.py
echo         logger.info("Advanced Security monitoring stopped at %%s", datetime.now()) >> modules\security\advanced\__init__.py

echo [INFO] Creo il file base del modulo stabilità...
echo # Stability module for M4Bot > modules\stability\__init__.py
echo. >> modules\stability\__init__.py
echo import logging >> modules\stability\__init__.py
echo from datetime import datetime >> modules\stability\__init__.py
echo. >> modules\stability\__init__.py
echo logger = logging.getLogger('m4bot.stability') >> modules\stability\__init__.py
echo. >> modules\stability\__init__.py
echo class StabilityMonitor: >> modules\stability\__init__.py
echo     def __init__(self): >> modules\stability\__init__.py
echo         logger.info("Stability monitor initialized at %%s", datetime.now()) >> modules\stability\__init__.py
echo. >> modules\stability\__init__.py
echo     def start_monitoring(self): >> modules\stability\__init__.py
echo         logger.info("Stability monitoring started at %%s", datetime.now()) >> modules\stability\__init__.py
echo. >> modules\stability\__init__.py
echo     def perform_self_healing(self): >> modules\stability\__init__.py
echo         logger.info("Self-healing procedure triggered at %%s", datetime.now()) >> modules\stability\__init__.py

echo [INFO] Imposto i permessi di tutti i file script...
attrib +x scripts\*.sh
attrib +x scripts\*.py
attrib +x *.py
attrib +x modules\*.py
attrib +x modules\security\*.py
attrib +x modules\stability\*.py

echo [INFO] Creo un file requirements.txt con le dipendenze necessarie...
echo flask>=2.3.0 > requirements.txt
echo Flask-Babel>=4.0.0 >> requirements.txt
echo Werkzeug>=2.3.0 >> requirements.txt
echo Jinja2>=3.1.2 >> requirements.txt
echo SQLAlchemy>=2.0.0 >> requirements.txt
echo psycopg2-binary>=2.9.5 >> requirements.txt
echo redis>=4.5.1 >> requirements.txt
echo requests>=2.28.2 >> requirements.txt
echo python-dotenv>=1.0.0 >> requirements.txt
echo pyyaml>=6.0 >> requirements.txt
echo cryptography>=40.0.0 >> requirements.txt
echo gunicorn>=20.1.0 >> requirements.txt

echo [SUCCESS] Installazione M4Bot corretta con successo!
echo.
echo Per avviare il sistema in ambiente Linux, esegui i seguenti comandi:
echo   sudo chmod +x scripts/*.sh
echo   sudo ./scripts/install.sh
echo.
echo Per avviare il sistema in ambiente Windows:
echo   1. Installa Python 3.9+ dal Microsoft Store o dal sito ufficiale
echo   2. Installa le dipendenze con: pip install -r requirements.txt
echo   3. Avvia il server con: python run.py
echo.
pause 