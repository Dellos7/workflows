---
description: Convertir rúbrica markdown a CSV
---


Cuando se ejecute este workflow, debes seguir de forma estricta las siguientes reglas. Tu objetivo será buscar en el archivo mencionado la rúbrica en Markdown (generalmente irá precedida de un título que dirá Rúbrica de lo que sea y estará al final del archivo .md mencionado) y generar la rúbrica en CSV, corrigiendo las partes que sean necesarias. Si se corrige algo, también debes corregirlo en el Markdown (archivo .md). Además, deberás generar el archivo .csv en la carpeta donde está el markdown mencionado con la rúbrica.

## 1. Validación previa obligatoria

Antes de generar el CSV:

* La suma de las puntuaciones máximas de los criterios propios de la actividad debe ser exactamente **10 puntos**.
* Las puntuaciones máximas de cada criterio deben ser **números enteros (sin decimales)**, distribuidas de forma lógica y ponderada según la dificultad o extensión de las tareas.
* Si la suma no es 10, se debe avisar del problema y **no generar el CSV** hasta corregirlo.
* La rúbrica debe incluir un **criterio negativo de entrega en plazo (penalización por retraso)** con una puntuación máxima de **0 puntos**. De esta forma, la actividad en sí valdrá 10 puntos, pero se restarán puntos en caso de entrega con retraso.

---

## 2. Formato CSV

* El separador de campos debe ser siempre **punto y coma (`;`)**.
* No deben aparecer punto y coma dentro de los textos descriptivos.
* Las comas sí están permitidas dentro de las descripciones (y como separador decimal si se requiere).
* La primera fila contiene los encabezados.

---

## 3. Orden de los niveles

Los niveles de desempeño deben aparecer siempre:

**De menor a mayor puntuación numérica**, es decir:

1. Nivel más bajo (puntuación más baja o más negativa)
2. Nivel intermedio bajo
3. Nivel intermedio alto
4. Nivel más alto (puntuación máxima)

Por ejemplo, para un criterio de contenido de 2 puntos:

| Nivel        | Puntos |
| ------------ | ------ |
| Insuficiente | 0      |
| Básico       | 0,5    |
| Adecuado     | 1      |
| Excelente    | 2      |

Por ejemplo, para el criterio negativo de entrega en plazo (máximo 0 puntos):

| Nivel                          | Puntos |
| ------------------------------ | ------ |
| No entrega / Retraso grave     | -2     |
| Entrega con retraso importante | -1,5   |
| Entrega con pequeño retraso    | -1     |
| Entrega en plazo               | 0      |

---

## 4. Estructura de columnas

Para cada criterio se utiliza una fila con esta estructura ampliable a más niveles:

```text
criterio;nivel1_def;nivel1_score;nivel2_def;nivel2_score;nivel3_def;nivel3_score;nivel4_def;nivel4_score
```

Donde:

* `criterio` → nombre del criterio.
* `nivel1_def` → descripción del nivel más bajo.
* `nivel1_score` → puntuación del nivel más bajo.
* `nivel2_def` → descripción del segundo nivel.
* `nivel2_score` → puntuación del segundo nivel.
* `nivel3_def` → descripción del tercer nivel.
* `nivel3_score` → puntuación del tercer nivel.
* `nivel4_def` → descripción del nivel más alto.
* `nivel4_score` → puntuación máxima del criterio.

y así en sucesivos niveles.

---

## 5. Distribución de puntuaciones

Para los criterios de la actividad:

* La suma de las puntuaciones máximas de los criterios propios de la actividad es exactamente **10 puntos**.
* Las puntuaciones asignadas a cada criterio no deben tener decimales (deben ser números enteros: 1, 2, 3, 4...).
* El nivel mínimo suele ser 0 puntos.
* Los niveles intermedios se reparten proporcionalmente.
* Las puntuaciones intermedias pueden tener decimales si es necesario.

Ejemplo para un criterio de 3 puntos:

| Nivel        | Puntos |
| ------------ | ------ |
| No realizado | 0      |
| Básico       | 1      |
| Adecuado     | 2      |
| Excelente    | 3      |

Ejemplo para un criterio de 2 puntos:

| Nivel        | Puntos |
| ------------ | ------ |
| No realizado | 0      |
| Básico       | 0,5    |
| Adecuado     | 1      |
| Excelente    | 2      |

Ejemplo para un criterio de 1 punto:

| Nivel        | Puntos |
| ------------ | ------ |
| No realizado | 0      |
| Básico       | 0,25   |
| Adecuado     | 0,5    |
| Excelente    | 1      |

---

## 6. Criterio de entrega en plazo (criterio negativo)

Todas las rúbricas deben incluir un criterio específico de penalización:

**Entrega en plazo**

Niveles habituales:

| Nivel                          | Puntuación |
| ------------------------------ | ---------- |
| No entrega o retraso grave     | -2         |
| Entrega con retraso importante | -1,5       |
| Entrega con pequeño retraso    | -1         |
| Entrega en plazo               | 0          |

* La puntuación máxima de este criterio debe ser **0 puntos** (asignada a la entrega en plazo).
* Los niveles con retraso tendrán puntuaciones negativas (restando hasta 2 puntos sobre la calificación final).

---

## 7. Encabezado CSV que solemos utilizar

```csv
criterio;nivel1_def;nivel1_score;nivel2_def;nivel2_score;nivel3_def;nivel3_score;nivel4_def;nivel4_score
```

---

## 8. Revisión final antes de entregar el CSV

Comprobar siempre:

* ✅ Separador `;`
* ✅ Niveles ordenados de menor a mayor puntuación numérica
* ✅ Sin punto y coma en las descripciones
* ✅ Suma total de criterios de contenido = 10 puntos
* ✅ Puntuaciones máximas de criterios de contenido sin decimales (números enteros)
* ✅ Existe criterio negativo de entrega en plazo
* ✅ Entrega en plazo tiene puntuación máxima de 0 puntos (y penalizaciones negativas como -2, -1,5, -1, 0)
* ✅ Cada criterio tiene sus 4 niveles completos (o correspondientes)
* ✅ La puntuación máxima del último nivel coincide con el peso del criterio (y 0 para la entrega en plazo)
