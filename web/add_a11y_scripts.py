#!/usr/bin/env python3
"""
Script per integrare gli script di accessibilità nelle pagine HTML
"""
import os
import sys
import re
import json
import argparse
from pathlib import Path

def find_html_files(root_dir):
    """Trova tutti i file HTML nella directory"""
    return list(Path(root_dir).glob('**/*.html')) + list(Path(root_dir).glob('**/*.htm'))

def add_scripts_to_file(file_path, script_paths, stylesheet_paths=None, before_tag='</body>'):
    """Aggiunge gli script e fogli di stile al file HTML prima del tag specificato"""
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Prepara tag per gli script
    script_tags = []
    for script in script_paths:
        script_tags.append(f'<script src="{script}"></script>')
    
    script_block = '\n    ' + '\n    '.join(script_tags)
    
    # Prepara tag per i fogli di stile
    style_tags = []
    if stylesheet_paths:
        for stylesheet in stylesheet_paths:
            style_tags.append(f'<link rel="stylesheet" href="{stylesheet}">')
        
    style_block = '\n    ' + '\n    '.join(style_tags) if style_tags else ''
    
    # Verifica se gli script sono già presenti
    missing_scripts = []
    for script in script_paths:
        if f'<script src="{script}"' not in content:
            missing_scripts.append(script)
    
    # Verifica se i fogli di stile sono già presenti
    missing_styles = []
    if stylesheet_paths:
        for stylesheet in stylesheet_paths:
            if f'<link rel="stylesheet" href="{stylesheet}"' not in content:
                missing_styles.append(stylesheet)
    
    if not missing_scripts and not missing_styles:
        print(f"  Tutti gli script e fogli di stile sono già presenti in {file_path}")
        return False
    
    # Aggiungi solo gli script mancanti
    missing_script_tags = []
    for script in missing_scripts:
        missing_script_tags.append(f'<script src="{script}"></script>')
    
    # Aggiungi solo i fogli di stile mancanti
    missing_style_tags = []
    for stylesheet in missing_styles:
        missing_style_tags.append(f'<link rel="stylesheet" href="{stylesheet}">')
    
    # Prepara i blocchi da inserire
    script_block = '\n    ' + '\n    '.join(missing_script_tags) if missing_script_tags else ''
    style_block = '\n    ' + '\n    '.join(missing_style_tags) if missing_style_tags else ''
    
    # Aggiungi i fogli di stile nell'head
    if style_block:
        head_tag = '</head>'
        if head_tag in content:
            content = content.replace(head_tag, f"{style_block}\n{head_tag}")
            print(f"  Fogli di stile aggiunti nell'head di {file_path}")
    
    # Aggiungi gli script prima del tag specificato
    if script_block:
        if before_tag in content:
            content = content.replace(before_tag, f"{script_block}\n{before_tag}")
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(content)
            print(f"  Script aggiunti a {file_path}")
            return True
        else:
            print(f"  ATTENZIONE: Tag '{before_tag}' non trovato in {file_path}")
    
    # Salva le modifiche se è stato aggiunto almeno uno stile
    if style_block and not script_block:
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(content)
        return True
    
    return False

def load_manifest(manifest_path):
    """Carica il manifest degli script"""
    try:
        with open(manifest_path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Errore nel caricamento del manifest: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Integra gli script di accessibilità nelle pagine HTML')
    parser.add_argument('--dir', default='templates', help='Directory contenente i file HTML')
    parser.add_argument('--manifest', default='static/js/a11y-manifest.json', help='Percorso del manifest degli script')
    parser.add_argument('--env', default='production', help='Ambiente (production, development, testing)')
    args = parser.parse_args()
    
    # Determina i percorsi
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(base_dir, args.dir)
    manifest_path = os.path.join(base_dir, args.manifest)
    
    # Carica il manifest
    manifest = load_manifest(manifest_path)
    if not manifest:
        sys.exit(1)
    
    # Filtra gli script da caricare in base all'ambiente
    scripts_to_load = []
    for script in manifest.get('scripts', []):
        if script.get('loadOnStart', False):
            # Controlla se lo script è limitato a certi ambienti
            script_env = script.get('environment', ['production', 'development', 'testing'])
            if args.env in script_env or not script_env:
                scripts_to_load.append('/static/js/' + script['file'])
    
    # Filtra i fogli di stile da caricare
    stylesheets_to_load = []
    for stylesheet in manifest.get('stylesheets', []):
        if stylesheet.get('loadOnStart', False):
            # Controlla se il foglio di stile è limitato a certi ambienti
            style_env = stylesheet.get('environment', ['production', 'development', 'testing'])
            if args.env in style_env or not style_env:
                stylesheets_to_load.append('/static/css/' + stylesheet['file'])
    
    if not scripts_to_load and not stylesheets_to_load:
        print("Nessuno script o foglio di stile da caricare per questo ambiente.")
        return
    
    # Trova tutti i file HTML
    html_files = find_html_files(template_dir)
    if not html_files:
        print(f"Nessun file HTML trovato in {template_dir}")
        return
    
    print(f"Trovati {len(html_files)} file HTML.")
    
    # Aggiungi gli script ai file HTML
    modified_count = 0
    for file_path in html_files:
        if add_scripts_to_file(file_path, scripts_to_load, stylesheets_to_load):
            modified_count += 1
    
    print(f"Script e fogli di stile aggiunti a {modified_count} file HTML su {len(html_files)}.")

if __name__ == "__main__":
    main() 