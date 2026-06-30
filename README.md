*Este proyecto ha sido creado como parte del currículo de 42 por gortiz-j.*

# Call Me Maybe

## Descripción

**Call Me Maybe** es un proyecto que explora las capacidades de los **Small Language Models (SLMs)** en el contexto del **Function Calling**. El objetivo es implementar un mecanismo robusto de **decodificación restringida (Constrained Decoding)** que obligue a un modelo generativo a producir un JSON válido estructurado de acuerdo con definiciones de funciones específicas.

Al restringir el proceso de generación del modelo, garantizamos que la salida siempre cumpla con el esquema requerido, haciéndola fiable para su integración programática, incluso con modelos pequeños y menos potentes.

---

## Instrucciones

### Requisitos previos

- Python 3.10 o superior
- Gestor de paquetes `uv`
- `make`
- **Más de 2 GB de almacenamiento** para descargar el modelo

### Instalación

Clona el repositorio e instala las dependencias utilizando el Makefile:

```bash
make install
```

Esto configurará un entorno virtual (utilizando `uv` si está disponible o el entorno estándar `venv`) e instalará `torch` y el resto de las dependencias.

### Ejecución

Para ejecutar la demostración principal de decodificación restringida:

```bash
make run
```

Esto ejecutará el programa utilizando los datos de entrada ubicados en `data/input/`.

También puedes ejecutarlo manualmente:

```bash
uv run python -m src
```

---

## Recursos

- **Hugging Face Transformers**: Documentación para la carga de modelos y la tokenización.
- **Modelo Qwen**: La familia de modelos Qwen, utilizada por su eficiencia.
- **Constrained Decoding**: Investigaciones y artículos sobre estrategias de generación basadas en máquinas de estados finitos (FSM).

### Uso de IA

Los asistentes de IA (GitHub Copilot) fueron utilizados en este proyecto para:

- **Crear la estructura inicial de la FSM:** Ayudar en el diseño de las transiciones de estado del parser JSON personalizado.
- **Depurar el manejo de tokens:** Ayudar a identificar problemas relacionados con codificaciones específicas de tokens y particularidades del tokenizador.
- **Refactorización:** Mejorar la modularidad del código entre el SDK del LLM y la lógica principal de la aplicación.

---

## Explicación del algoritmo

El núcleo de este proyecto es un algoritmo de **decodificación restringida** basado en una **Máquina de Estados Finitos (FSM)**.

1. **Definición de estados:** El proceso de generación se divide en estados detallados (por ejemplo, `START`, `OPEN_QUOTE_FN_KEY`, `FN_VALUE`, `ARG_VALUE`, etc.) definidos en la enumeración `Stage`.

2. **Enmascaramiento de logits:** En cada paso de la generación, el algoritmo inspecciona el estado actual.

   - Si se espera un token de sintaxis específico (como `"` o `:`), únicamente se permite el ID correspondiente a ese token.
   - Si se espera el nombre de una función (`FN_VALUE`), solo se permiten los tokens que continúan válidamente el nombre de alguna función conocida, utilizando una estrategia de coincidencia por prefijos.
   - Si se espera un valor (`ARG_VALUE`), los tokens permitidos se restringen según el tipo del argumento (por ejemplo, únicamente dígitos para un `int`, o excluyendo las comillas para cadenas que aún no han finalizado).

3. **Guiado determinista:** Los logits originales del modelo se enmascaran (los tokens no permitidos se establecen en `-∞` o simplemente se excluyen), de manera que la probabilidad solo se asigna a los siguientes tokens válidos. Esto obliga al modelo a mantenerse dentro del esquema JSON válido definido por las funciones disponibles.

---

## Decisiones de diseño

- **FSM en lugar de expresiones regulares:** Se eligió una máquina de estados explícita en lugar de restricciones basadas en expresiones regulares para obtener un control más preciso sobre las transiciones de estado y facilitar la integración de lógica personalizada, como la validación dinámica de los argumentos de las funciones.

- **Modelo pequeño (`Qwen/Qwen3-0.6B`):** Se eligió deliberadamente un modelo pequeño para demostrar que, con restricciones suficientemente fuertes, incluso modelos ligeros pueden realizar tareas estructuradas que normalmente requieren modelos mucho más grandes.

- **Enmascaramiento de tokens en tiempo de generación:** Las restricciones se aplican directamente sobre los logits durante la generación, evitando que el modelo tome caminos inválidos antes incluso de que sean muestreados.

- **Optimización del cálculo de la máscara:** Como la máscara siempre contiene menos elementos que el vocabulario completo, los logits se calculan sobre el menor número posible de tokens para mejorar la eficiencia (esta operación puede tardar hasta **0,6 segundos** por iteración).

---

## Análisis de rendimiento

- **Precisión:** La salida es un **JSON sintácticamente correcto al 100%**. Este enfoque garantiza que, siempre que se produzca una salida, esta cumplirá el esquema definido.

- **Velocidad:** La sobrecarga de comprobar la FSM en cada paso de generación es mínima en comparación con el tiempo de inferencia del modelo.

- **Fiabilidad:** Extremadamente alta en cuanto al cumplimiento estructural. La corrección funcional (es decir, elegir la función adecuada) depende de la comprensión del *prompt* por parte del modelo, pero el **formato** está garantizado.

---

## Desafíos encontrados

- **Particularidades del tokenizador:** Gestionar la forma en que distintos tokenizadores representan los espacios iniciales o caracteres especiales (como `Ġ`) supuso un desafío importante al intentar hacer coincidir exactamente los nombres de las funciones.

- **Complejidad de los estados:** Gestionar la compleja jerarquía de estados del JSON (objetos anidados, validación de tipos de argumentos, etc.) requirió un diseño muy cuidadoso de la máquina de estados.

- **Coincidencia parcial de tokens:** Implementar un mecanismo que permitiera al modelo generar nombres de funciones compuestos por varios tokens, produciéndolos uno a uno.

---

## Estrategia de pruebas

- **Pruebas unitarias:** Se realizaron pruebas utilizando un conjunto de *prompts* (`function_calling_tests.json`) que cubren diversos casos límite.

- **Validación del esquema:** La salida de cada ejecución se analiza como JSON. La prueba falla si el resultado no puede interpretarse como JSON o si no coincide con la estructura esperada (aunque la FSM hace que esto sea muy poco probable).

---

## Ejemplo de uso

**Prompt de entrada:**

```text
Get the weather for Paris.
```

El sistema restringe la salida para que coincida con la definición disponible de la función `get_weather`.

**Salida del modelo (JSON garantizado):**

```json
{
  "function": "get_weather",
  "args": {
    "location": "Paris",
    "unit": "celsius"
  }
}
```