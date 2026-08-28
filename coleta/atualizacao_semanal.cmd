@echo off
REM Disparado pelo Agendador de Tarefas do Windows, aos sábados.
REM O log de cada execução fica em publicacao.log, ao lado deste arquivo.
cd /d "%~dp0"
"C:\Users\Matheus Menegatti\AppData\Local\Microsoft\WindowsApps\python.exe" publicar_automatico.py >> publicacao_saida.log 2>&1
