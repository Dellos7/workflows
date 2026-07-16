---
description: Regenerar JSON de MD de Programación de Aula
---

Cuando se ejecute este workflow, quiero que regeneres el archivo JSON mencionado. El JSON tendrá una estructura similar a esta (EJEMPLO):

{
  "version": "1.0",
  "docType": "SITUACION",
  "teacherContext": {
    "subject": "Digitalització",
    "gradeLevel": "4ºESO",
    "academicYear": "2026-27",
    "weeklyHours": 3,
    "language": "Castellano",
    "selectedNeeds": [
      "Dislexia / DEA",
      "Medidas Nivel III (Apoyo específico)",
      "Desconocimiento del idioma"
    ],
    "otherNeeds": "",
    "methodologyPreference": [
      "Aprendizaje Basado en Proyectos (ABP)",
      "Instrucción Directa y Práctica",
      "Aprendizaje Basado en Retos"
    ],
    "methodologyDescription": "La principal metodología que utilizo yo es el aprendizaje a través de actividades prácticas. El alumnado aprende a base de realizar prácticas en ordenador en forma de actividades que debe entregar para su evaluación y calificación.",
    "generateFullCourse": true,
    "fullCourseIdeas": "Quiero enseñarles acerca de sistemas operativos y máquinas virtuales. Esta quiero que sea la SA1 (primera unidad del curso). \n\nQuiero que el alumnado aprenda a generar contenido que le pueda resultar útil (documentos y hojas de cálculo) e integrarlo en actividades con contenido interesante del curso. Me gustaría que esta fuera la SA2 (segunda unidad del curso). \n\nQuiero que el alumnado aprenda acerca de los componentes de un ordenador (hardware) y su montaje con piezas (no disponemos de material físico para poder planificar actividades de montaje, así que debe ser algo simulado). \n\nQuiero que el alumnado aprenda acerca de la representación digital de la información (cómo se codifica, sistema binario, hexadecimal, bits, bytes, etc). \n\nQuiero que aprendan conceptos básicos y necesarios de IA y también utilizar la IA de forma segura y útil. \n\nMe gustaría incluir conceptos de seguridad y privacidad en la red, y enseñarlos de forma práctica e interactiva. \n\nQuiero enseñarles algo de programación, que no sea Scratch ni por bloques. Quizá algo enfocado a videojuegos, algo simple pero potente con GDevelop o similar ",
    "numberOfSAs": 2,
    "saDetails": [
      {
        "idea": "",
        "sessions": "",
        "competencies": [],
        "blocks": []
      },
      {
        "idea": "",
        "sessions": "",
        "competencies": [],
        "blocks": []
      }
    ]
  },
  "analysisData": {
    "subject": "Digitalització",
    "grade": "4ºESO",
    "competencies": [
      "CE1: Dissenyar equips i xarxes de comunicació d’ús personal i domèstic, administrar-los i utilitzar-los de manera segura i sostenible.",
      "CE2: Buscar, seleccionar i organitzar la informació en l’entorn personal d’aprenentatge, i utilitzar-la per a la creació, edició, publicació i difusió de continguts digitals.",
      "CE3: Mostrar hàbits que fomenten el benestar en entorns digitals, aplicant mesures preventives i correctives per a protegir dispositius, dades personals i la pròpia salut.",
      "CE4: Exercir una ciutadania digital crítica mitjançant un ús actiu, responsable i ètic dels mitjans digitals, el comerç electrònic i l’administració digital en la societat de la informació.",
      "CE5: Afrontar els desafiaments informàtics i digitals que la societat de la informació planteja en els àmbits personal, domèstic i educatiu, i formular possibles solucions."
    ],
    "blocks": [
      "Bloque 1: Dispositius digitals, sistemes operatius i de comunicació",
      "Bloque 2: Digitalització de l’entorn personal d’aprenentatge",
      "Bloque 3: Seguretat i benestar digital",
      "Bloque 4: Ciutadania digital crítica"
    ]
  },
  "content": "",
  "teacherName": "David López",
  "department": "Informática",
  "activities": []
}

Dentro de "content" habrá que colocar el nuevo contenido markdown del archivo .md mencionado y reajustar el resto de campos y variables de forma adecuada haciendo un análisis del contenido del .md mencionado, que será el contenido como tal de la Programación de Aula.

Se pueden hacer las preguntas que se consideren necesarias al usuario.