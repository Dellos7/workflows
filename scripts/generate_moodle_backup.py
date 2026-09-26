#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_moodle_backup.py
Generador de copias de seguridad de Moodle (.mbz) para Aules (Moodle 5.2.1+).
Genera la estructura de cursos, secciones (temas), botón web interactivo,
y tareas (assign) enlazando a las actividades de la web, con soporte para
duplicación y restricción por grupos (ej. DIG1, DIG2).
"""

import os
import sys
import re
import json
import time
import argparse
import tarfile
import shutil
import hashlib
import urllib.parse
import urllib.request
import mimetypes
from pathlib import Path
import xml.etree.ElementTree as ET
import xml.sax.saxutils as saxutils

def find_course_overview_image(subject_dir, config, temp_dir=None):
    """
    Localiza la imagen para 'Archivos del resumen del curso' (overviewfiles en Moodle).
    Busca por orden:
    1. Campo explícito en JSON ('course_image', 'course.course_image', 'course.image', 'overview_image', etc.)
       Admite rutas relativas, absolutas o URLs web (http/https).
    2. Etiqueta con <img> en la sección general (Banner)
    3. Coincidencia por slug o nombre en archivos/imagenes/
    """
    subject_dir = Path(subject_dir).resolve()
    repo_root = subject_dir.parent.parent  # informatica-eso-bat/
    archivos_img_dir = repo_root / "archivos" / "imagenes"
    archivos_dir = repo_root / "archivos"

    course_obj = config.get("course", {}) if isinstance(config.get("course"), dict) else {}

    # 1. Configuración explícita (en course o en la raíz del config)
    explicit = (
        config.get("course_image") or
        course_obj.get("course_image") or
        course_obj.get("image") or
        config.get("overview_image") or
        course_obj.get("overview_image") or
        config.get("overview_file")
    )

    def resolve_candidate(cand_str):
        if not cand_str or not isinstance(cand_str, str):
            return None
        cand_str = cand_str.strip()
        if not cand_str:
            return None

        # Si es una URL http/https
        if cand_str.lower().startswith(("http://", "https://")):
            parsed = urllib.parse.urlparse(cand_str)
            raw_path = urllib.parse.unquote(parsed.path)
            fname = Path(raw_path).name
            if fname:
                for loc in [
                    archivos_img_dir / fname,
                    archivos_dir / fname,
                    subject_dir / fname,
                    repo_root / raw_path.lstrip("/\\")
                ]:
                    if loc.is_file():
                        return loc
            # Si no está localmente, intentar descargarla
            try:
                dest = (temp_dir / f"downloaded_overview_{fname}") if temp_dir else (archivos_img_dir / fname)
                urllib.request.urlretrieve(cand_str, dest)
                if dest.is_file() and dest.stat().st_size > 0:
                    return dest
            except Exception as e:
                print(f"[!] Aviso: No se pudo descargar la imagen desde URL '{cand_str}': {e}")
            return None

        # Si es una ruta local
        p = Path(cand_str)
        if p.is_file():
            return p
        if (subject_dir / cand_str).is_file():
            return subject_dir / cand_str
        if (archivos_img_dir / p.name).is_file():
            return archivos_img_dir / p.name
        if (archivos_dir / p.name).is_file():
            return archivos_dir / p.name
        return None

    resolved_explicit = resolve_candidate(explicit)
    if resolved_explicit:
        return resolved_explicit

    # 2. Extraer del Banner en general_section.activities
    for act in config.get("general_section", {}).get("activities", []):
        content = act.get("content") or act.get("intro") or ""
        m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content, re.IGNORECASE)
        if m:
            img_src = m.group(1).strip()
            res = resolve_candidate(img_src)
            if res:
                return res

    # 3. Búsqueda por slug en archivos/imagenes
    if archivos_img_dir.is_dir():
        slug = subject_dir.name.lower()
        for f in archivos_img_dir.iterdir():
            if f.is_file() and f.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp'):
                f_clean = f.stem.lower().replace("-", "").replace("_", "")
                slug_clean = slug.replace("-", "").replace("_", "")
                if slug_clean in f_clean or f_clean in slug_clean:
                    return f

    return None


def escape_xml(text):
    """Escapa caracteres especiales para inclusión segura en XML."""
    if text is None:
        return ""
    return saxutils.escape(str(text), {
        '"': "&quot;",
        "'": "&apos;"
    })

def clean_markdown_title(title_text):
    """Limpia caracteres de markdown innecesarios en un título."""
    if not title_text:
        return ""
    # Quitar enlaces markdown tipo [Texto](url) -> Texto
    t = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', title_text)
    # Quitar marcas de negrita o cursiva
    t = re.sub(r'[*_~`]', '', t)
    return t.strip()

def parse_rubric_csv(csv_path):
    """
    Parsea un archivo rubrica.csv siguiendo el formato de Moodle / convertir-rubrica-csv.
    Retorna una lista de criterios con sus niveles:
    [
        {
            "criterion": "1. Estructura de carpetas y Compresión",
            "levels": [
                {"score": 0.0, "definition": "..."},
                {"score": 0.5, "definition": "..."},
                ...
            ]
        },
        ...
    ]
    """
    import csv
    criteria = []
    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            sample = f.read(2048)
            f.seek(0)
            delimiter = ";" if ";" in sample else ","
            reader = csv.reader(f, delimiter=delimiter)
            header = next(reader, None)
            if not header:
                return []

            for row in reader:
                if not row or not any(cell.strip() for cell in row):
                    continue
                criterion_name = row[0].strip()
                if not criterion_name:
                    continue

                levels = []
                col = 1
                while col < len(row):
                    def_text = row[col].strip() if col < len(row) else ""
                    score_str = row[col + 1].strip() if col + 1 < len(row) else ""
                    col += 2

                    if not def_text and not score_str:
                        continue

                    score_val = 0.0
                    if score_str:
                        try:
                            score_val = float(score_str.replace(",", "."))
                        except ValueError:
                            score_val = 0.0

                    levels.append({
                        "score": score_val,
                        "definition": def_text
                    })

                if levels:
                    levels.sort(key=lambda l: l["score"])
                    criteria.append({
                        "criterion": criterion_name,
                        "levels": levels
                    })
    except Exception as e:
        print(f"[-] Advertencia al leer rúbrica {csv_path}: {e}", file=sys.stderr)
        return []

    return criteria

def discover_subject_data(subject_dir, config, web_base_url):
    """
    Descubre o combina los temas y actividades a partir de la configuración
    y de la estructura de archivos en la carpeta de la asignatura.
    """
    subject_slug = subject_dir.name
    topics_cfg = config.get("topics")
    discovered_topics = []

    if topics_cfg:
        # Usar la lista de temas proporcionada en el JSON
        for t in topics_cfg:
            discovered_topics.append(t)
    else:
        # Autodescubrimiento a partir de index.md de la asignatura
        index_path = subject_dir / "index.md"
        if index_path.exists():
            with open(index_path, "r", encoding="utf-8") as f:
                content = f.read()
            for line in content.splitlines():
                # Formato típico: - [Tema 1](./sistemas-operativos) o - [Tema 1](./sistemas-operativos/)
                m = re.match(r"^\s*-\s*\[([^\]]+)\]\(\./([^/)]+)/?\)", line)
                if m:
                    discovered_topics.append({
                        "title": clean_markdown_title(m.group(1)),
                        "folder": m.group(2).strip()
                    })
        
        # Si no se encontraron temas en index.md, buscar subcarpetas con index.md
        if not discovered_topics:
            for item in sorted(subject_dir.iterdir()):
                if item.is_dir() and not item.name.startswith((".", "_", "archivos", "capturas", "assets")):
                    if (item / "index.md").exists():
                        discovered_topics.append({
                            "title": item.name.replace("-", " ").capitalize(),
                            "folder": item.name
                        })

    # Procesar cada tema y sus actividades
    processed_topics = []
    for sec_idx, t in enumerate(discovered_topics, start=1):
        folder_name = t.get("folder", "")
        tdir = subject_dir / folder_name if folder_name else None
        
        sec_title = t.get("title", f"Tema {sec_idx}")
        # Intentar obtener título más descriptivo desde el index.md del tema si existe
        if tdir and tdir.exists():
            tindex = tdir / "index.md"
            if tindex.exists():
                with open(tindex, "r", encoding="utf-8") as tif:
                    tc = tif.read()
                # Buscar encabezado H1 (# ...)
                h1 = re.search(r"^#\s+(.+)$", tc, re.MULTILINE)
                if h1:
                    sec_title = clean_markdown_title(h1.group(1))

        # Determinar URL del tema
        topic_url = t.get("web_url")
        if not topic_url:
            topic_url = f"{web_base_url}/{folder_name}" if folder_name else web_base_url

        # Actividades del tema
        topic_acts = t.get("activities")
        if topic_acts is None and tdir and tdir.exists():
            topic_acts = []
            for item in sorted(tdir.iterdir()):
                if item.is_dir() and not item.name.startswith((".", "_", "capturas", "archivos", "assets")):
                    act_idx = item / "index.md"
                    if act_idx.exists():
                        with open(act_idx, "r", encoding="utf-8") as af:
                            ac = af.read()
                        act_t = item.name
                        # 1. Mirar frontmatter YAML title
                        fm = re.search(r"^---\s*\n(.*?)\n---", ac, re.DOTALL)
                        if fm:
                            tm = re.search(r"^title:\s*(.+)$", fm.group(1), re.MULTILINE)
                            if tm:
                                act_t = tm.group(1).strip().strip('"\'')
                        # 2. Si no había frontmatter title, mirar primer H1
                        if act_t == item.name:
                            h1 = re.search(r"^#\s+(.+)$", ac, re.MULTILINE)
                            if h1:
                                act_t = h1.group(1).strip()
                        
                        act_url = f"{topic_url}/{item.name}/"

                        # Buscar archivo de rúbrica en la carpeta de la actividad
                        rubric_data = None
                        for csv_cand in [item / "rubrica.csv", item / "rúbrica.csv", item / "Rubrica.csv", item / "Rúbrica.csv"]:
                            if csv_cand.exists():
                                rubric_data = parse_rubric_csv(csv_cand)
                                break
                        if not rubric_data:
                            for f in item.glob("*.csv"):
                                if "rubric" in f.name.lower() or "rúbric" in f.name.lower():
                                    rubric_data = parse_rubric_csv(f)
                                    break

                        topic_acts.append({
                            "folder": item.name,
                            "title": clean_markdown_title(act_t),
                            "web_url": act_url,
                            "rubric": rubric_data
                        })

        # Si las actividades ya venían en la configuración, asegurar que buscan su rúbrica si no la tienen
        if topic_acts and tdir and tdir.exists():
            for act_item in topic_acts:
                if not act_item.get("rubric"):
                    act_folder = act_item.get("folder")
                    if act_folder:
                        af_path = tdir / act_folder
                        if af_path.exists():
                            for csv_cand in [af_path / "rubrica.csv", af_path / "rúbrica.csv", af_path / "Rubrica.csv", af_path / "Rúbrica.csv"]:
                                if csv_cand.exists():
                                    act_item["rubric"] = parse_rubric_csv(csv_cand)
                                    break

        # Parámetro para visibilidad del tema / sección
        raw_sec_vis = t.get(
            "visible",
            t.get("section_visible",
                  t.get("mostrar_seccion",
                        t.get("mostrar_tema", True)))
        )
        sec_vis = False if raw_sec_vis in (0, False, "0", "false") else True

        # Parámetro para visibilidad de las actividades del tema
        raw_acts_vis = t.get(
            "activities_visible",
            t.get("activities_visibility",
                  t.get("actividades_visibles",
                        t.get("mostrar_actividades",
                              config.get("activities_visible", True))))
        )
        acts_vis = False if raw_acts_vis in (0, False, "0", "false") else True

        # Parámetro para mostrar la descripción de las actividades en la página del curso
        show_act_desc = t.get(
            "show_activity_description",
            t.get("show_activities_description",
                  t.get("show_description",
                        t.get("showdescription",
                              t.get("mostrar_descripcion_actividades",
                                    t.get("mostrar_descripcion",
                                          config.get("show_activity_description", False))))))
        )

        processed_topics.append({
            "section_number": sec_idx,
            "title": sec_title,
            "folder": folder_name,
            "web_url": topic_url,
            "button_text": t.get("button_text", f"TEMA {sec_idx} (WEB)"),
            "show_activity_description": bool(show_act_desc),
            "visible": sec_vis,
            "activities_visible": acts_vis,
            "activities": topic_acts or []
        })

    return processed_topics

def generate_mbz(subject_dir, config_path=None, output_mbz_path=None, web_base_url_override=None):
    """
    Función principal de generación del archivo .mbz importable en Moodle 5.2.
    """
    subject_dir = Path(subject_dir).resolve()
    if not subject_dir.exists():
        raise FileNotFoundError(f"No se encuentra la carpeta de la asignatura: {subject_dir}")

    subject_slug = subject_dir.name

    # Cargar configuración JSON si existe
    config = {}
    config_file_found = None
    if config_path and Path(config_path).exists():
        config_file_found = Path(config_path).resolve()
    else:
        candidate = subject_dir / f"config_backup_moodle_{subject_slug}.json"
        if candidate.exists():
            config_file_found = candidate
        else:
            # Probar también config_backup_moodle.json genérico
            generic_cand = subject_dir / "config_backup_moodle.json"
            if generic_cand.exists():
                config_file_found = generic_cand

    if config_file_found:
        print(f"[*] Usando archivo de configuración: {config_file_found}")
        with open(config_file_found, "r", encoding="utf-8") as f:
            config = json.load(f)
    else:
        print(f"[*] No se encontró configuración previa. Se usarán valores por defecto para '{subject_slug}'.")

    # Determinar metadatos del curso
    course_cfg = config.get("course", {})
    fullname = course_cfg.get("fullname", f"Asignatura - {subject_slug.capitalize()}")
    shortname = course_cfg.get("shortname", subject_slug.upper())
    idnumber = course_cfg.get("idnumber", f"{subject_slug.upper()}_AUTO")
    summary = course_cfg.get("summary", "")

    # URL base de la web
    web_base_url = (web_base_url_override or 
                    config.get("web_base_url") or 
                    f"https://dlopezcastellote.dev/informatica-eso-bat/asignaturas/{subject_slug}").rstrip("/")

    # Gestión de grupos
    raw_groups = config.get("groups", [])
    groups = []
    for i, g in enumerate(raw_groups):
        if isinstance(g, str):
            groups.append({"id": 1000 + i, "name": g})
        elif isinstance(g, dict):
            groups.append({
                "id": g.get("id", 1000 + i),
                "name": g.get("name", f"Grupo {i+1}")
            })

    duplicate_per_group = config.get("duplicate_activities_per_group", len(groups) > 0)
    if groups:
        print(f"[*] Grupos configurados ({len(groups)}): {[g['name'] for g in groups]} (Duplicar tareas: {duplicate_per_group})")
    else:
        print("[*] Sin grupos configurados. Las tareas se crearán de forma única sin restricciones.")

    # Estilo del botón web
    btn_style = config.get("topic_button", {}).get(
        "style",
        "display: inline-block; padding: 14px 28px; font-family: 'Segoe UI', Roboto, sans-serif; "
        "font-size: 16px; font-weight: 600; letter-spacing: 0.5px; color: #ffffff; "
        "background-color: #0076ff; text-decoration: none; border-radius: 8px; "
        "box-shadow: 0 4px 6px rgba(0, 118, 255, 0.2); transition: background-color 0.2s ease;"
    )

    # Descubrir temas y actividades
    topics = discover_subject_data(subject_dir, config, web_base_url)
    print(f"[*] Se procesarán {len(topics)} temas.")

    # Timestamp para fecha y hora de la copia
    now_ts = int(time.time())
    backup_date = now_ts
    timestamp_str = time.strftime("%Y%m%d_%H%M%S", time.localtime(now_ts))

    # Ruta de salida .mbz
    if not output_mbz_path:
        archivos_dir = subject_dir.parent.parent / "archivos"
        if (archivos_dir / "backups").exists():
            dest_dir = archivos_dir / "backups"
        elif archivos_dir.exists():
            dest_dir = archivos_dir
        else:
            dest_dir = subject_dir
        output_mbz_path = dest_dir / f"backup_moodle_{subject_slug}_{timestamp_str}.mbz"
    else:
        out_p = Path(output_mbz_path)
        if out_p.is_dir() or str(output_mbz_path).endswith(("\\", "/")):
            output_mbz_path = out_p / f"backup_moodle_{subject_slug}_{timestamp_str}.mbz"
        else:
            if out_p.suffix.lower() == ".mbz":
                # Si ya termina en .mbz, añadir fecha y hora al final del nombre base antes de .mbz
                output_mbz_path = out_p.with_name(f"{out_p.stem}_{timestamp_str}.mbz")
            else:
                output_mbz_path = out_p.with_name(f"{out_p.name}_{timestamp_str}.mbz")
    output_mbz_path = Path(output_mbz_path).resolve()

    # Directorio temporal de staging
    temp_dir = output_mbz_path.parent / f"_temp_moodle_build_{subject_slug}_{now_ts}"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    try:
        # Asignación de identificadores de backup
        next_cmid = 4000001
        next_act_id = 1000001
        next_context_id = 5000001
        next_grade_item_id = 1400001
        next_area_id = 1100001
        next_definition_id = 100001
        next_criterion_id = 500001
        next_level_id = 2000001
        next_file_id = 6000001
        course_id = 130792
        course_context_id = 5592653

        sections_data = []
        activities_data = []

        # Sección 0: General (Requerida en Moodle)
        sec0_id = 700000
        sec0_sequence = []

        general_config = config.get("general_section", {})
        gen_activities = general_config.get("activities", [])

        for g_act in gen_activities:
            act_type = g_act.get("type", "label")
            act_name = g_act.get("name", "Recurso")
            raw_act_vis = g_act.get("visible", 1)
            act_visible = 0 if raw_act_vis in (0, False, "0", "false") else 1
            cmid = next_cmid; next_cmid += 1
            act_id = next_act_id; next_act_id += 1
            ctx_id = next_context_id; next_context_id += 1

            sec0_sequence.append(cmid)

            if act_type == "label":
                intro = g_act.get("content", g_act.get("intro", ""))
                activities_data.append({
                    "moduleid": cmid,
                    "sectionid": sec0_id,
                    "sectionnumber": 0,
                    "modulename": "label",
                    "title": act_name,
                    "directory": f"activities/label_{cmid}",
                    "instance_id": act_id,
                    "contextid": ctx_id,
                    "intro": intro,
                    "visible": act_visible,
                    "availability": "$@NULL@$"
                })
            elif act_type == "url":
                external_url = g_act.get("external_url", g_act.get("url", ""))
                intro = g_act.get("intro", "")
                activities_data.append({
                    "moduleid": cmid,
                    "sectionid": sec0_id,
                    "sectionnumber": 0,
                    "modulename": "url",
                    "title": act_name,
                    "directory": f"activities/url_{cmid}",
                    "instance_id": act_id,
                    "contextid": ctx_id,
                    "intro": intro,
                    "externalurl": external_url,
                    "visible": act_visible,
                    "availability": "$@NULL@$"
                })
            elif act_type == "forum":
                forum_type = g_act.get("forum_type", "news")
                intro = g_act.get("intro", "Anuncis i notícies generals")
                activities_data.append({
                    "moduleid": cmid,
                    "sectionid": sec0_id,
                    "sectionnumber": 0,
                    "modulename": "forum",
                    "title": act_name,
                    "directory": f"activities/forum_{cmid}",
                    "instance_id": act_id,
                    "contextid": ctx_id,
                    "intro": intro,
                    "forumtype": forum_type,
                    "visible": act_visible,
                    "availability": "$@NULL@$"
                })

        sections_data.append({
            "id": sec0_id,
            "number": 0,
            "name": "$@NULL@$",
            "sequence": sec0_sequence,
            "directory": f"sections/section_{sec0_id}"
        })

        # Procesar cada tema
        for t in topics:
            sec_idx = t["section_number"]
            sec_id = 700000 + sec_idx
            sec_title = t["title"]
            topic_url = t["web_url"]
            btn_text = t.get("button_text", f"TEMA {sec_idx} (WEB)")
            topic_show_desc = t.get("show_activity_description", False)

            sec_sequence = []

            # 1. Crear el botón HTML al tema web (recurso Label / Etiqueta)
            btn_html = f'<p style="text-align: center;"><a style="{btn_style}" href="{topic_url}" target="_blank" rel="noopener noreferrer"> {btn_text} </a></p>'
            
            label_cmid = next_cmid; next_cmid += 1
            label_act_id = next_act_id; next_act_id += 1
            label_ctx_id = next_context_id; next_context_id += 1

            sec_sequence.append(label_cmid)
            activities_data.append({
                "moduleid": label_cmid,
                "sectionid": sec_id,
                "sectionnumber": sec_idx,
                "modulename": "label",
                "title": f"Enlace Web Asignatura - Tema {sec_idx}",
                "directory": f"activities/label_{label_cmid}",
                "instance_id": label_act_id,
                "contextid": label_ctx_id,
                "intro": btn_html,
                "availability": "$@NULL@$"
            })

            # 2. Crear las actividades de entrega (recurso Assign / Tarea)
            target_groups = groups if (duplicate_per_group and groups) else [None]
            topic_acts_visible = t.get("activities_visible", True)

            for act in t["activities"]:
                act_title = act["title"]
                act_url = act.get("web_url") or f"{topic_url}/{act.get('folder', '')}/"
                intro_html = f'<p><strong>➡️ACTIVIDAD</strong>: <a href="{act_url}" target="_blank" rel="noopener">{act_url}</a></p>'

                act_show_desc = act.get("show_activity_description", act.get("show_description", topic_show_desc))
                show_desc_int = 1 if act_show_desc else 0

                raw_act_vis = act.get("visible", topic_acts_visible)
                act_vis_int = 0 if raw_act_vis in (0, False, "0", "false") else 1

                for grp in target_groups:
                    assign_cmid = next_cmid; next_cmid += 1
                    assign_act_id = next_act_id; next_act_id += 1
                    assign_ctx_id = next_context_id; next_context_id += 1
                    grade_item_id = next_grade_item_id; next_grade_item_id += 1

                    sec_sequence.append(assign_cmid)

                    avail_xml = "$@NULL@$"
                    if grp is not None:
                        avail_json = json.dumps({
                            "op": "&",
                            "c": [{"type": "group", "id": grp["id"]}],
                            "showc": [True]
                        })
                        avail_xml = escape_xml(avail_json)

                    activities_data.append({
                        "moduleid": assign_cmid,
                        "sectionid": sec_id,
                        "sectionnumber": sec_idx,
                        "modulename": "assign",
                        "title": act_title,
                        "directory": f"activities/assign_{assign_cmid}",
                        "instance_id": assign_act_id,
                        "contextid": assign_ctx_id,
                        "grade_item_id": grade_item_id,
                        "intro": intro_html,
                        "availability": avail_xml,
                        "group": grp,
                        "rubric": act.get("rubric"),
                        "showdescription": show_desc_int,
                        "visible": act_vis_int
                    })

            sec_vis_int = 0 if t.get("visible", True) in (0, False, "0", "false") else 1
            sections_data.append({
                "id": sec_id,
                "number": sec_idx,
                "name": sec_title,
                "sequence": sec_sequence,
                "directory": f"sections/section_{sec_id}",
                "visible": sec_vis_int
            })

        # Estructura de carpetas en staging
        (temp_dir / "activities").mkdir()
        (temp_dir / "sections").mkdir()
        (temp_dir / "course").mkdir()
        (temp_dir / "files").mkdir()

        # Manejo de la imagen de resumen del curso (overviewfiles en Moodle)
        overview_img_path = find_course_overview_image(subject_dir, config, temp_dir)
        files_xml_entries = []
        course_fileref_entries = []

        if overview_img_path and overview_img_path.is_file():
            img_bytes = overview_img_path.read_bytes()
            img_hash = hashlib.sha1(img_bytes).hexdigest()
            img_size = len(img_bytes)
            img_name = overview_img_path.name
            img_mime = mimetypes.guess_type(img_name)[0] or "image/png"

            # Copiar archivo al directorio files/<hash[:2]>/<hash>
            hash_sub = temp_dir / "files" / img_hash[:2]
            hash_sub.mkdir(parents=True, exist_ok=True)
            (hash_sub / img_hash).write_bytes(img_bytes)

            file_id_img = next_file_id; next_file_id += 1
            file_id_dot = next_file_id; next_file_id += 1

            files_xml_entries.append(f'''  <file id="{file_id_img}">
    <contenthash>{img_hash}</contenthash>
    <contextid>{course_context_id}</contextid>
    <component>course</component>
    <filearea>overviewfiles</filearea>
    <itemid>0</itemid>
    <filepath>/</filepath>
    <filename>{escape_xml(img_name)}</filename>
    <userid>108277</userid>
    <filesize>{img_size}</filesize>
    <mimetype>{img_mime}</mimetype>
    <status>0</status>
    <timecreated>{now_ts}</timecreated>
    <timemodified>{now_ts}</timemodified>
    <source>{escape_xml(img_name)}</source>
    <author>David López Castellote</author>
    <license>unknown</license>
    <sortorder>0</sortorder>
    <repositorytype>$@NULL@$</repositorytype>
    <repositoryid>$@NULL@$</repositoryid>
    <reference>$@NULL@$</reference>
  </file>''')

            files_xml_entries.append(f'''  <file id="{file_id_dot}">
    <contenthash>da39a3ee5e6b4b0d3255bfef95601890afd80709</contenthash>
    <contextid>{course_context_id}</contextid>
    <component>course</component>
    <filearea>overviewfiles</filearea>
    <itemid>0</itemid>
    <filepath>/</filepath>
    <filename>.</filename>
    <userid>108277</userid>
    <filesize>0</filesize>
    <mimetype>$@NULL@$</mimetype>
    <status>0</status>
    <timecreated>{now_ts}</timecreated>
    <timemodified>{now_ts}</timemodified>
    <source>$@NULL@$</source>
    <author>$@NULL@$</author>
    <license>$@NULL@$</license>
    <sortorder>0</sortorder>
    <repositorytype>$@NULL@$</repositorytype>
    <repositoryid>$@NULL@$</repositoryid>
    <reference>$@NULL@$</reference>
  </file>''')

            course_fileref_entries.append(f'''  <fileref>
    <file>
      <id>{file_id_img}</id>
    </file>
    <file>
      <id>{file_id_dot}</id>
    </file>
  </fileref>''')
            print(f"[*] Imagen de resumen del curso configurada: {img_name} ({img_size / 1024:.1f} KB)")

        # Archivos XML de la raíz
        (temp_dir / "badges.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<badges>\n</badges>', encoding="utf-8")
        (temp_dir / "scales.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<scales_definition>\n</scales_definition>', encoding="utf-8")
        (temp_dir / "outcomes.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<outcomes_definition>\n</outcomes_definition>', encoding="utf-8")
        (temp_dir / "questions.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<question_categories>\n</question_categories>', encoding="utf-8")
        if files_xml_entries:
            files_xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n<files>\n' + "\n".join(files_xml_entries) + "\n</files>"
        else:
            files_xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n<files>\n</files>'
        (temp_dir / "files.xml").write_text(files_xml_content, encoding="utf-8")
        (temp_dir / "moodle_backup.log").write_text("", encoding="utf-8")

        # roles.xml
        (temp_dir / "roles.xml").write_text('''<?xml version="1.0" encoding="UTF-8"?>
<roles_definition>
  <role id="5">
    <name></name>
    <shortname>student</shortname>
    <nameincourse>$@NULL@$</nameincourse>
    <description></description>
    <sortorder>5</sortorder>
    <archetype>student</archetype>
  </role>
</roles_definition>''', encoding="utf-8")

        # groups.xml
        grp_xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<groups>']
        for g in groups:
            grp_xml.append(f'''  <group id="{g['id']}">
    <name>{escape_xml(g['name'])}</name>
    <idnumber></idnumber>
    <description></description>
    <descriptionformat>1</descriptionformat>
    <enrolmentkey></enrolmentkey>
    <picture>0</picture>
    <visibility>0</visibility>
    <participation>1</participation>
    <timecreated>{now_ts}</timecreated>
    <timemodified>{now_ts}</timemodified>
    <group_members>
    </group_members>
  </group>''')
        grp_xml.append('  <groupcustomfields>\n  </groupcustomfields>\n  <groupings>\n    <groupingcustomfields>\n    </groupingcustomfields>\n  </groupings>\n</groups>')
        (temp_dir / "groups.xml").write_text("\n".join(grp_xml), encoding="utf-8")

        # Archivos de course/
        (temp_dir / "course" / "calendar.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<events>\n</events>', encoding="utf-8")
        (temp_dir / "course" / "completiondefaults.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<course_completion_defaults>\n</course_completion_defaults>', encoding="utf-8")
        (temp_dir / "course" / "contentbank.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<contents>\n</contents>', encoding="utf-8")
        (temp_dir / "course" / "filters.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<filters>\n  <filter_actives>\n  </filter_actives>\n  <filter_configs>\n  </filter_configs>\n</filters>', encoding="utf-8")
        (temp_dir / "course" / "roles.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<roles>\n  <role_overrides>\n  </role_overrides>\n  <role_assignments>\n  </role_assignments>\n</roles>', encoding="utf-8")

        # course/enrolments.xml
        (temp_dir / "course" / "enrolments.xml").write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<enrolments>
  <enrols>
    <enrol id="402446">
      <enrol>manual</enrol>
      <status>0</status>
      <name>$@NULL@$</name>
      <enrolperiod>0</enrolperiod>
      <enrolstartdate>0</enrolstartdate>
      <enrolenddate>0</enrolenddate>
      <expirynotify>0</expirynotify>
      <expirythreshold>86400</expirythreshold>
      <notifyall>0</notifyall>
      <password>$@NULL@$</password>
      <cost>$@NULL@$</cost>
      <currency>$@NULL@$</currency>
      <roleid>5</roleid>
      <timecreated>{now_ts}</timecreated>
      <timemodified>{now_ts}</timemodified>
      <user_enrolments>
      </user_enrolments>
    </enrol>
  </enrols>
</enrolments>''', encoding="utf-8")

        # course/inforef.xml
        cinf = ['<?xml version="1.0" encoding="UTF-8"?>', '<inforef>', '  <groupref>']
        for g in groups:
            cinf.append(f'    <group>\n      <id>{g["id"]}</id>\n    </group>')
        cinf.append('  </groupref>\n  <roleref>\n    <role>\n      <id>5</id>\n    </role>\n  </roleref>')
        if course_fileref_entries:
            cinf.extend(course_fileref_entries)
        cinf.append('</inforef>')
        (temp_dir / "course" / "inforef.xml").write_text("\n".join(cinf), encoding="utf-8")

        # course/course.xml
        (temp_dir / "course" / "course.xml").write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<course id="{course_id}" contextid="{course_context_id}">
  <shortname>{escape_xml(shortname)}</shortname>
  <fullname>{escape_xml(fullname)}</fullname>
  <idnumber>{escape_xml(idnumber)}</idnumber>
  <summary>{escape_xml(summary)}</summary>
  <summaryformat>1</summaryformat>
  <format>topics</format>
  <showgrades>1</showgrades>
  <newsitems>5</newsitems>
  <startdate>{now_ts}</startdate>
  <enddate>{now_ts + 31536000}</enddate>
  <marker>0</marker>
  <maxbytes>0</maxbytes>
  <legacyfiles>0</legacyfiles>
  <showreports>0</showreports>
  <visible>1</visible>
  <groupmode>0</groupmode>
  <groupmodeforce>0</groupmodeforce>
  <defaultgroupingid>0</defaultgroupingid>
  <lang></lang>
  <theme></theme>
  <timecreated>{now_ts}</timecreated>
  <timemodified>{now_ts}</timemodified>
  <requested>0</requested>
  <showactivitydates>1</showactivitydates>
  <showcompletionconditions>1</showcompletionconditions>
  <pdfexportfont>$@NULL@$</pdfexportfont>
  <enablecompletion>1</enablecompletion>
  <completionnotify>0</completionnotify>
  <enableaitools>$@NULL@$</enableaitools>
  <category id="1">
    <name>General</name>
    <description></description>
  </category>
  <tags>
  </tags>
  <customfields>
  </customfields>
  <courseformatoptions>
    <courseformatoption>
      <format>topics</format>
      <sectionid>0</sectionid>
      <name>hiddensections</name>
      <value>0</value>
    </courseformatoption>
    <courseformatoption>
      <format>topics</format>
      <sectionid>0</sectionid>
      <name>coursedisplay</name>
      <value>0</value>
    </courseformatoption>
  </courseformatoptions>
</course>''', encoding="utf-8")

        # sections/
        for sec in sections_data:
            sdir = temp_dir / sec["directory"]
            sdir.mkdir(parents=True)
            (sdir / "inforef.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<inforef>\n</inforef>', encoding="utf-8")
            seq_str = ",".join(str(x) for x in sec["sequence"])
            name_val = "$@NULL@$" if sec["name"] == "$@NULL@$" else escape_xml(sec["name"])
            (sdir / "section.xml").write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<section id="{sec['id']}">
  <number>{sec['number']}</number>
  <name>{name_val}</name>
  <summary></summary>
  <summaryformat>1</summaryformat>
  <sequence>{seq_str}</sequence>
  <visible>{sec.get('visible', 1)}</visible>
  <availabilityjson>$@NULL@$</availabilityjson>
  <component>$@NULL@$</component>
  <itemid>$@NULL@$</itemid>
  <timemodified>{now_ts}</timemodified>
</section>''', encoding="utf-8")

        # activities/
        for act in activities_data:
            adir = temp_dir / act["directory"]
            adir.mkdir(parents=True)

            # module.xml
            (adir / "module.xml").write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<module id="{act['moduleid']}" version="2026042000">
  <modulename>{act['modulename']}</modulename>
  <sectionid>{act['sectionid']}</sectionid>
  <sectionnumber>{act['sectionnumber']}</sectionnumber>
  <idnumber></idnumber>
  <added>{now_ts}</added>
  <score>0</score>
  <indent>0</indent>
  <visible>{act.get('visible', 1)}</visible>
  <visibleoncoursepage>1</visibleoncoursepage>
  <visibleold>{act.get('visible', 1)}</visibleold>
  <groupmode>0</groupmode>
  <groupingid>0</groupingid>
  <completion>{2 if act['modulename'] == 'assign' else 0}</completion>
  <completiongradeitemnumber>$@NULL@$</completiongradeitemnumber>
  <completionpassgrade>0</completionpassgrade>
  <completionview>0</completionview>
  <completionexpected>0</completionexpected>
  <availability>{act['availability']}</availability>
  <showdescription>{1 if act['modulename'] == 'label' else act.get('showdescription', 0)}</showdescription>
  <downloadcontent>1</downloadcontent>
  <lang></lang>
  <enableaitools>$@NULL@$</enableaitools>
  <enabledaiactions>$@NULL@$</enabledaiactions>
  <tags>
  </tags>
</module>''', encoding="utf-8")

            # Archivos auxiliares comunes
            (adir / "roles.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<roles>\n  <role_overrides>\n  </role_overrides>\n  <role_assignments>\n  </role_assignments>\n</roles>', encoding="utf-8")
            (adir / "filters.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<filters>\n  <filter_actives>\n  </filter_actives>\n  <filter_configs>\n  </filter_configs>\n</filters>', encoding="utf-8")
            (adir / "calendar.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<events>\n</events>', encoding="utf-8")
            (adir / "grade_history.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<grade_history>\n  <grade_grades>\n  </grade_grades>\n</grade_history>', encoding="utf-8")

            if act["modulename"] == "label":
                (adir / "label.xml").write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<activity id="{act['instance_id']}" moduleid="{act['moduleid']}" modulename="label" contextid="{act['contextid']}">
  <label id="{act['instance_id']}">
    <name>{escape_xml(act['title'])}</name>
    <intro>{escape_xml(act['intro'])}</intro>
    <introformat>1</introformat>
    <timemodified>{now_ts}</timemodified>
  </label>
</activity>''', encoding="utf-8")
                (adir / "grades.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<activity_gradebook>\n  <grade_items>\n  </grade_items>\n  <grade_letters>\n  </grade_letters>\n</activity_gradebook>', encoding="utf-8")
                (adir / "inforef.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<inforef>\n</inforef>', encoding="utf-8")

            elif act["modulename"] == "url":
                (adir / "url.xml").write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<activity id="{act['instance_id']}" moduleid="{act['moduleid']}" modulename="url" contextid="{act['contextid']}">
  <url id="{act['instance_id']}">
    <name>{escape_xml(act['title'])}</name>
    <intro>{escape_xml(act.get('intro', ''))}</intro>
    <introformat>1</introformat>
    <externalurl>{escape_xml(act.get('externalurl', ''))}</externalurl>
    <display>5</display>
    <displayoptions>a:0:{{}}</displayoptions>
    <parameters>a:0:{{}}</parameters>
    <timemodified>{now_ts}</timemodified>
  </url>
</activity>''', encoding="utf-8")
                (adir / "grades.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<activity_gradebook>\n  <grade_items>\n  </grade_items>\n  <grade_letters>\n  </grade_letters>\n</activity_gradebook>', encoding="utf-8")
                (adir / "inforef.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<inforef>\n</inforef>', encoding="utf-8")

            elif act["modulename"] == "forum":
                (adir / "forum.xml").write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<activity id="{act['instance_id']}" moduleid="{act['moduleid']}" modulename="forum" contextid="{act['contextid']}">
  <forum id="{act['instance_id']}">
    <type>{act.get('forumtype', 'news')}</type>
    <name>{escape_xml(act['title'])}</name>
    <intro>{escape_xml(act.get('intro', ''))}</intro>
    <introformat>1</introformat>
    <duedate>0</duedate>
    <cutoffdate>0</cutoffdate>
    <assessed>0</assessed>
    <assesstimestart>0</assesstimestart>
    <assesstimefinish>0</assesstimefinish>
    <scale>0</scale>
    <maxbytes>0</maxbytes>
    <maxattachments>1</maxattachments>
    <forcesubscribe>1</forcesubscribe>
    <trackingtype>1</trackingtype>
    <rsstype>0</rsstype>
    <rssarticles>0</rssarticles>
    <timemodified>{now_ts}</timemodified>
    <warnafter>0</warnafter>
    <blockafter>0</blockafter>
    <blockperiod>0</blockperiod>
    <completiondiscussions>0</completiondiscussions>
    <completionreplies>0</completionreplies>
    <completionposts>0</completionposts>
    <displaywordcount>0</displaywordcount>
    <lockdiscussionafter>0</lockdiscussionafter>
    <grade_forum>0</grade_forum>
    <showimmediately>0</showimmediately>
    <discussions>
    </discussions>
    <subscriptions>
    </subscriptions>
    <digests>
    </digests>
    <readposts>
    </readposts>
    <trackedprefs>
    </trackedprefs>
    <poststags>
    </poststags>
    <grades>
    </grades>
  </forum>
</activity>''', encoding="utf-8")
                (adir / "grading.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<areas>\n</areas>', encoding="utf-8")
                (adir / "grades.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<activity_gradebook>\n  <grade_items>\n  </grade_items>\n  <grade_letters>\n  </grade_letters>\n</activity_gradebook>', encoding="utf-8")
                (adir / "inforef.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<inforef>\n</inforef>', encoding="utf-8")

            elif act["modulename"] == "assign":
                rubric = act.get("rubric")
                if rubric:
                    area_id = next_area_id; next_area_id += 1
                    def_id = next_definition_id; next_definition_id += 1
                    rubric_title = f"Rúbrica - {act['title']}"

                    crit_xml_list = []
                    for c_idx, c in enumerate(rubric, start=1):
                        crit_id = next_criterion_id; next_criterion_id += 1
                        crit_desc = escape_xml(c["criterion"])

                        lvl_xml_list = []
                        for lvl in c["levels"]:
                            lvl_id = next_level_id; next_level_id += 1
                            lvl_score = f"{lvl['score']:.5f}"
                            lvl_def = escape_xml(lvl["definition"])
                            lvl_xml_list.append(f'''                <level id="{lvl_id}">
                  <score>{lvl_score}</score>
                  <definition>{lvl_def}</definition>
                  <definitionformat>0</definitionformat>
                </level>''')

                        levels_block = "\n".join(lvl_xml_list)
                        crit_xml_list.append(f'''            <criterion id="{crit_id}">
              <sortorder>{c_idx}</sortorder>
              <description>{crit_desc}</description>
              <descriptionformat>0</descriptionformat>
              <levels>
{levels_block}
              </levels>
            </criterion>''')

                    criteria_block = "\n".join(crit_xml_list)
                    grading_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<areas>
  <area id="{area_id}">
    <areaname>submissions</areaname>
    <activemethod>rubric</activemethod>
    <definitions>
      <definition id="{def_id}">
        <method>rubric</method>
        <name>{escape_xml(rubric_title)}</name>
        <description></description>
        <descriptionformat>1</descriptionformat>
        <status>20</status>
        <timecreated>{now_ts}</timecreated>
        <timemodified>{now_ts}</timemodified>
        <options>{{"sortlevelsasc":"1","lockzeropoints":"1","alwaysshowdefinition":"1","showdescriptionteacher":"1","showdescriptionstudent":"1","showscoreteacher":"1","showscorestudent":"1","enableremarks":"1","showremarksstudent":"1"}}</options>
        <plugin_gradingform_rubric_definition>
          <criteria>
{criteria_block}
          </criteria>
        </plugin_gradingform_rubric_definition>
        <instances>
        </instances>
      </definition>
    </definitions>
  </area>
</areas>'''
                    (adir / "grading.xml").write_text(grading_content, encoding="utf-8")
                else:
                    (adir / "grading.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<areas>\n</areas>', encoding="utf-8")

                (adir / "inforef.xml").write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<inforef>
  <grade_itemref>
    <grade_item>
      <id>{act['grade_item_id']}</id>
    </grade_item>
  </grade_itemref>
</inforef>''', encoding="utf-8")
                (adir / "grades.xml").write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<activity_gradebook>
  <grade_items>
    <grade_item id="{act['grade_item_id']}">
      <categoryid>1</categoryid>
      <itemname>{escape_xml(act['title'])}</itemname>
      <itemtype>mod</itemtype>
      <itemmodule>assign</itemmodule>
      <iteminstance>{act['instance_id']}</iteminstance>
      <itemnumber>0</itemnumber>
      <iteminfo>$@NULL@$</iteminfo>
      <idnumber></idnumber>
      <calculation>$@NULL@$</calculation>
      <gradetype>1</gradetype>
      <grademax>10.00000</grademax>
      <grademin>0.00000</grademin>
      <scaleid>$@NULL@$</scaleid>
      <outcomeid>$@NULL@$</outcomeid>
      <gradepass>5.00000</gradepass>
      <multfactor>1.00000</multfactor>
      <plusfactor>0.00000</plusfactor>
      <aggregationcoef>1.00000</aggregationcoef>
      <aggregationcoef2>0.00000</aggregationcoef2>
      <weightoverride>0</weightoverride>
      <sortorder>1</sortorder>
      <display>0</display>
      <decimals>$@NULL@$</decimals>
      <hidden>0</hidden>
      <locked>0</locked>
      <locktime>0</locktime>
      <needsupdate>0</needsupdate>
      <timecreated>{now_ts}</timecreated>
      <timemodified>{now_ts}</timemodified>
      <grade_grades>
      </grade_grades>
    </grade_item>
  </grade_items>
  <grade_letters>
  </grade_letters>
</activity_gradebook>''', encoding="utf-8")

                (adir / "assign.xml").write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<activity id="{act['instance_id']}" moduleid="{act['moduleid']}" modulename="assign" contextid="{act['contextid']}">
  <assign id="{act['instance_id']}">
    <name>{escape_xml(act['title'])}</name>
    <intro>{escape_xml(act['intro'])}</intro>
    <introformat>1</introformat>
    <alwaysshowdescription>1</alwaysshowdescription>
    <submissiondrafts>0</submissiondrafts>
    <sendnotifications>0</sendnotifications>
    <sendlatenotifications>0</sendlatenotifications>
    <sendstudentnotifications>1</sendstudentnotifications>
    <duedate>0</duedate>
    <cutoffdate>0</cutoffdate>
    <gradingduedate>0</gradingduedate>
    <allowsubmissionsfromdate>0</allowsubmissionsfromdate>
    <grade>10</grade>
    <timemodified>{now_ts}</timemodified>
    <completionsubmit>1</completionsubmit>
    <requiresubmissionstatement>0</requiresubmissionstatement>
    <teamsubmission>0</teamsubmission>
    <requireallteammemberssubmit>0</requireallteammemberssubmit>
    <teamsubmissiongroupingid>0</teamsubmissiongroupingid>
    <blindmarking>0</blindmarking>
    <hidegrader>0</hidegrader>
    <revealidentities>0</revealidentities>
    <attemptreopenmethod>untilpass</attemptreopenmethod>
    <maxattempts>1</maxattempts>
    <markingworkflow>0</markingworkflow>
    <markingallocation>0</markingallocation>
    <markercount>1</markercount>
    <multimarkmethod>$@NULL@$</multimarkmethod>
    <markinganonymous>0</markinganonymous>
    <preventsubmissionnotingroup>0</preventsubmissionnotingroup>
    <activity></activity>
    <activityformat>1</activityformat>
    <timelimit>0</timelimit>
    <submissionattachments>0</submissionattachments>
    <gradepenalty>0</gradepenalty>
    <userflags>
    </userflags>
    <allocatedmarkers>
    </allocatedmarkers>
    <submissions>
    </submissions>
    <grades>
    </grades>
    <marks>
    </marks>
    <plugin_configs>
      <plugin_config id="{act['instance_id']}01">
        <plugin>file</plugin>
        <subtype>assignsubmission</subtype>
        <name>enabled</name>
        <value>1</value>
      </plugin_config>
      <plugin_config id="{act['instance_id']}02">
        <plugin>file</plugin>
        <subtype>assignsubmission</subtype>
        <name>maxfilesubmissions</name>
        <value>20</value>
      </plugin_config>
      <plugin_config id="{act['instance_id']}03">
        <plugin>file</plugin>
        <subtype>assignsubmission</subtype>
        <name>maxsubmissionsizebytes</name>
        <value>52428800</value>
      </plugin_config>
      <plugin_config id="{act['instance_id']}04">
        <plugin>file</plugin>
        <subtype>assignsubmission</subtype>
        <name>filetypeslist</name>
        <value></value>
      </plugin_config>
      <plugin_config id="{act['instance_id']}05">
        <plugin>comments</plugin>
        <subtype>assignsubmission</subtype>
        <name>enabled</name>
        <value>1</value>
      </plugin_config>
      <plugin_config id="{act['instance_id']}06">
        <plugin>comments</plugin>
        <subtype>assignfeedback</subtype>
        <name>enabled</name>
        <value>1</value>
      </plugin_config>
      <plugin_config id="{act['instance_id']}07">
        <plugin>comments</plugin>
        <subtype>assignfeedback</subtype>
        <name>commentinline</name>
        <value>0</value>
      </plugin_config>
      <plugin_config id="{act['instance_id']}08">
        <plugin>editpdf</plugin>
        <subtype>assignfeedback</subtype>
        <name>enabled</name>
        <value>0</value>
      </plugin_config>
      <plugin_config id="{act['instance_id']}09">
        <plugin>file</plugin>
        <subtype>assignfeedback</subtype>
        <name>enabled</name>
        <value>0</value>
      </plugin_config>
      <plugin_config id="{act['instance_id']}10">
        <plugin>onlinetext</plugin>
        <subtype>assignsubmission</subtype>
        <name>enabled</name>
        <value>0</value>
      </plugin_config>
      <plugin_config id="{act['instance_id']}11">
        <plugin>offline</plugin>
        <subtype>assignfeedback</subtype>
        <name>enabled</name>
        <value>0</value>
      </plugin_config>
    </plugin_configs>
    <overrides>
    </overrides>
  </assign>
</activity>''', encoding="utf-8")

        # moodle_backup.xml
        mb_xml = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<moodle_backup>',
            '  <information>',
            f'    <name>{output_mbz_path.name}</name>',
            '    <moodle_version>2026042001.04</moodle_version>',
            '    <moodle_release>5.2.1+ (Build: 20260630)</moodle_release>',
            '    <backup_version>2026042000</backup_version>',
            '    <backup_release>5.2</backup_release>',
            f'    <backup_date>{backup_date}</backup_date>',
            '    <mnet_remoteusers>0</mnet_remoteusers>',
            '    <include_files>1</include_files>',
            '    <include_file_references_to_external_content>0</include_file_references_to_external_content>',
            '    <original_wwwroot>https://aules.edu.gva.es/docent</original_wwwroot>',
            '    <original_site_identifier_hash>276defd03abf8ae32f54c6bf719ce3f6</original_site_identifier_hash>',
            f'    <original_course_id>{course_id}</original_course_id>',
            '    <original_course_format>topics</original_course_format>',
            f'    <original_course_fullname>{escape_xml(fullname)}</original_course_fullname>',
            f'    <original_course_shortname>{escape_xml(shortname)}</original_course_shortname>',
            f'    <original_course_startdate>{now_ts}</original_course_startdate>',
            f'    <original_course_enddate>{now_ts + 31536000}</original_course_enddate>',
            f'    <original_course_contextid>{course_context_id}</original_course_contextid>',
            '    <original_system_contextid>1</original_system_contextid>',
            '    <details>',
            '      <detail backup_id="55fadf0de7ef105324aa319f67730a5a">',
            '        <type>course</type>',
            '        <format>moodle2</format>',
            '        <interactive>1</interactive>',
            '        <mode>10</mode>',
            '        <execution>1</execution>',
            '        <executiontime>0</executiontime>',
            '      </detail>',
            '    </details>',
            '    <contents>',
            '      <activities>'
        ]

        for act in activities_data:
            mb_xml.append(f'''        <activity>
          <moduleid>{act['moduleid']}</moduleid>
          <sectionid>{act['sectionid']}</sectionid>
          <modulename>{act['modulename']}</modulename>
          <title>{escape_xml(act['title'])}</title>
          <directory>{act['directory']}</directory>
          <insubsection></insubsection>
        </activity>''')

        mb_xml.append('      </activities>\n      <sections>')
        for sec in sections_data:
            sec_title_val = "0" if sec["number"] == 0 else escape_xml(sec["name"])
            mb_xml.append(f'''        <section>
          <sectionid>{sec['id']}</sectionid>
          <title>{sec_title_val}</title>
          <directory>{sec['directory']}</directory>
          <parentcmid />
          <modname />
        </section>''')

        mb_xml.append(f'''      </sections>
      <course>
        <courseid>{course_id}</courseid>
        <title>{escape_xml(fullname)}</title>
        <directory>course</directory>
      </course>
    </contents>
    <settings>
      <setting>
        <level>root</level>
        <name>filename</name>
        <value>{output_mbz_path.name}</value>
      </setting>
      <setting>
        <level>root</level>
        <name>imscc11</name>
        <value>0</value>
      </setting>
      <setting>
        <level>root</level>
        <name>users</name>
        <value>0</value>
      </setting>
      <setting>
        <level>root</level>
        <name>anonymize</name>
        <value>0</value>
      </setting>
      <setting>
        <level>root</level>
        <name>role_assignments</name>
        <value>0</value>
      </setting>
      <setting>
        <level>root</level>
        <name>activities</name>
        <value>1</value>
      </setting>
      <setting>
        <level>root</level>
        <name>blocks</name>
        <value>1</value>
      </setting>
      <setting>
        <level>root</level>
        <name>files</name>
        <value>1</value>
      </setting>
      <setting>
        <level>root</level>
        <name>filters</name>
        <value>1</value>
      </setting>
      <setting>
        <level>root</level>
        <name>comments</name>
        <value>0</value>
      </setting>
      <setting>
        <level>root</level>
        <name>badges</name>
        <value>1</value>
      </setting>
      <setting>
        <level>root</level>
        <name>calendarevents</name>
        <value>1</value>
      </setting>
      <setting>
        <level>root</level>
        <name>userscompletion</name>
        <value>0</value>
      </setting>
      <setting>
        <level>root</level>
        <name>logs</name>
        <value>0</value>
      </setting>
      <setting>
        <level>root</level>
        <name>grade_histories</name>
        <value>0</value>
      </setting>
      <setting>
        <level>root</level>
        <name>groups</name>
        <value>1</value>
      </setting>
      <setting>
        <level>root</level>
        <name>competencies</name>
        <value>0</value>
      </setting>
      <setting>
        <level>root</level>
        <name>customfield</name>
        <value>1</value>
      </setting>
      <setting>
        <level>root</level>
        <name>contentbankcontent</name>
        <value>1</value>
      </setting>
      <setting>
        <level>root</level>
        <name>xapistate</name>
        <value>0</value>
      </setting>
      <setting>
        <level>root</level>
        <name>legacyfiles</name>
        <value>1</value>
      </setting>''')

        for sec in sections_data:
            mb_xml.append(f'''      <setting>
        <level>section</level>
        <section>section_{sec['id']}</section>
        <name>section_{sec['id']}_included</name>
        <value>1</value>
      </setting>
      <setting>
        <level>section</level>
        <section>section_{sec['id']}</section>
        <name>section_{sec['id']}_userinfo</name>
        <value>0</value>
      </setting>''')

        for act in activities_data:
            act_base = Path(act["directory"]).name
            mb_xml.append(f'''      <setting>
        <level>activity</level>
        <activity>{act_base}</activity>
        <name>{act_base}_included</name>
        <value>1</value>
      </setting>
      <setting>
        <level>activity</level>
        <activity>{act_base}</activity>
        <name>{act_base}_userinfo</name>
        <value>0</value>
      </setting>''')

        mb_xml.append('    </settings>\n  </information>\n</moodle_backup>')
        (temp_dir / "moodle_backup.xml").write_text("\n".join(mb_xml), encoding="utf-8")

        # Validar todos los XML antes de empaquetar
        for root_p, _, files in os.walk(temp_dir):
            for f in files:
                if f.endswith(".xml"):
                    xml_path = Path(root_p) / f
                    try:
                        ET.parse(xml_path)
                    except Exception as ex:
                        raise ValueError(f"Error de sintaxis XML en {xml_path.name}: {ex}")

        # Construir .ARCHIVE_INDEX
        all_items = []
        for root_p, dirs, files in os.walk(temp_dir):
            rel_root = Path(root_p).relative_to(temp_dir)
            for d in sorted(dirs):
                rel_path = (rel_root / d).as_posix() + "/"
                all_items.append((rel_path, "d", 0, "?"))
            for f in sorted(files):
                if f == ".ARCHIVE_INDEX":
                    continue
                f_path = Path(root_p) / f
                rel_path = (rel_root / f).as_posix()
                size = f_path.stat().st_size
                mtime = int(f_path.stat().st_mtime)
                all_items.append((rel_path, "f", size, mtime))

        all_items.sort(key=lambda x: x[0])

        index_lines = [f"Moodle archive file index. Count: {len(all_items)}"]
        for path_str, kind, size, mtime in all_items:
            index_lines.append(f"{path_str}\t{kind}\t{size}\t{mtime}")

        index_content = "\n".join(index_lines) + "\n"
        (temp_dir / ".ARCHIVE_INDEX").write_text(index_content, encoding="utf-8")

        # Empaquetar en archivo .mbz (tar.gz) en formato POSIX USTAR estricto (sin @PaxHeader)
        output_mbz_path.parent.mkdir(parents=True, exist_ok=True)

        def tar_filter(ti):
            ti.uid = 0
            ti.gid = 0
            ti.uname = ""
            ti.gname = ""
            ti.mtime = int(ti.mtime)
            return ti

        with tarfile.open(output_mbz_path, "w:gz", format=tarfile.USTAR_FORMAT) as tar:
            # 1. Cabecera .ARCHIVE_INDEX obligatoriamente primera
            tar.add(temp_dir / ".ARCHIVE_INDEX", arcname=".ARCHIVE_INDEX", filter=tar_filter)

            # 2. Agregar cada elemento en el orden exacto del índice con recursive=False
            for path_str, _, _, _ in all_items:
                item_clean_name = path_str.rstrip("/")
                local_path = temp_dir / item_clean_name
                tar.add(local_path, arcname=item_clean_name, recursive=False, filter=tar_filter)

        print(f"\n[+] COPIA DE SEGURIDAD GENERADA CON ÉXITO:")
        print(f"    Ruta: {output_mbz_path}")
        print(f"    Tamaño: {output_mbz_path.stat().st_size / 1024:.1f} KB")
        print(f"    Secciones (temas): {len(sections_data) - 1}")
        print(f"    Actividades creadas: {len(activities_data)}")
        rubrics_count = sum(1 for a in activities_data if a.get("rubric"))
        print(f"    Rúbricas aplicadas: {rubrics_count}")
        if overview_img_path and overview_img_path.is_file():
            print(f"    Imagen del curso (resumen): {overview_img_path.name}")
        return output_mbz_path

    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

def main():
    parser = argparse.ArgumentParser(description="Generador de copias de seguridad de Moodle (.mbz) para Aules.")
    parser.add_argument("subject_dir", help="Ruta a la carpeta de la asignatura (ej. informatica-eso-bat/asignaturas/digitalizacion)")
    parser.add_argument("--config", "-c", help="Ruta opcional al archivo JSON de configuración")
    parser.add_argument("--output", "-o", help="Ruta opcional para el archivo .mbz generado")
    parser.add_argument("--base-url", "-u", help="URL base de la web para enlaces")

    args = parser.parse_args()
    try:
        generate_mbz(args.subject_dir, args.config, args.output, args.base_url)
    except Exception as e:
        print(f"[-] ERROR: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
