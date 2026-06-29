# *Este proyecto ha sido creado como parte del currículo de 42 por yousenna*

# Call Me Maybe: Introducción al Function Calling en LLMs
![Arquitectura de Decodificación Restringida](constrained_decoding.png)

## Descripción

El objetivo principal de este proyecto es cerrar la brecha entre el lenguaje humano no estructurado y la ejecución estructurada por computadora. Cuando se recibe una consulta como *"¿Cuál es la suma de 2 y 3?"*, los modelos de lenguaje pequeños tradicionales (como el modelo de 0.6B de parámetros utilizado aquí) suelen tener dificultades para generar JSON sintácticamente válido de forma consistente.

Este proyecto resuelve ese problema implementando una capa de **Decodificación Restringida (Constrained Decoding)**. En lugar de confiar en que el modelo formatee correctamente su respuesta, mi programa guía al modelo token por token. De esta manera, la salida cumple al **100%** con los esquemas definidos en el archivo de definición de funciones.

---

## Instrucciones

Este proyecto requiere **Python 3.10** o una versión superior. Las dependencias se gestionan mediante `uv`.

### Instalación

Para instalar las dependencias del proyecto dentro de un entorno virtual:

```bash
uv sync
```

### Ejecución

Ejecuta el programa especificando el archivo de definición de funciones, el archivo de pruebas y la ruta de salida:

```bash
uv run python -m src \
  --functions_definition data/input/functions_definition.json \
  --input data/input/function_calling_tests.json \
  --output data/output/function_calls.json
```

O puedes ejecutarlo directamente con:

```bash
make run
```

Por defecto, esto ejecutará el programa utilizando el modelo Qwen `'Qwen/Qwen3-0.6B'`, pero también puedes utilizar el modelo del bonus `'Qwen/Qwen2.5-1.5B-Instruct'` ejecutando:

```bash
make bonus
```

### Limpieza

Para eliminar archivos temporales, directorios de caché (`__pycache__`, `.mypy_cache`) y carpetas de compilación:

```bash
make clean
```

### Estilo de código y verificación

Para ejecutar el análisis estático y las comprobaciones de tipos:

```bash
make lint
```

---

## Recursos

- [Documentación de Python 3](https://docs.python.org/3/)
- [Documentación del módulo JSON](https://docs.python.org/3/library/json.html)
- [Documentación de Pydantic](https://pydantic-docs.helpmanual.io/)
- [Manejo de errores en Python](https://docs.python.org/3/tutorial/errors.html)

- [Documentación de Pydantic V2](https://docs.pydantic.dev/latest/)
- [Tokenizers de Hugging Face Transformers](https://huggingface.co/docs/tokenizers/index)
- [Conceptos del algoritmo Byte Pair Encoding (BPE)](https://huggingface.co/docs/transformers/tokenizer_summary)

- **Uso de IA:** La IA fue utilizada como mentor conceptual para comprender los logits, la tokenización y las matemáticas detrás del enmascaramiento en la decodificación restringida. Ningún fragmento de código fue copiado directamente desde la IA; toda la lógica y las implementaciones en Python fueron diseñadas, escritas y depuradas por el autor con el objetivo de lograr una comprensión profunda. Además, la IA ayudó con los *docstrings* de funciones, clases y métodos, así como con la generación del archivo README.

---

## Explicación del algoritmo

El núcleo del proyecto se basa en **Constrained Decoding** mediante **Logits Masking**, controlado por una **Máquina de Estados del Parser**.

```text
[ Contexto + Prefijo ] ──> [ Logits del LLM (151.643 puntuaciones) ]
                                 │
                                 ▼
              [ Aplicar máscara según el estado ] (Tokens inválidos = -inf)
                                 │
                                 ▼
                 [ Seleccionar el Argmax ] (ID entero)
                                 │
                                 ▼
            [ Añadir el ID a la lista de tokens ] ──> Repetir / Decodificar
```

1. **Seguimiento del estado:** El programa controla en qué parte de la estructura JSON se encuentra (por ejemplo, `SELECTING_FUNCTION`, `WRITING_PARAMETER_KEY` o `GENERATING_VALUE`).

2. **Intercepción de logits:** En cada paso de generación, el modelo produce las puntuaciones (*logits*) para todo el vocabulario (151.643 tokens).

3. **Enmascaramiento:** Según el estado actual, identifico todos los IDs de tokens válidos para el siguiente paso (por ejemplo, si se espera un número, únicamente son válidos los dígitos, el punto decimal o el signo menos). Los logits correspondientes a todos los tokens **inválidos** se establecen en $-\infty$.

4. **Selección mediante Argmax:** Busco el índice con la puntuación más alta dentro del vector de logits enmascarado. De este modo, el modelo queda obligado a seleccionar un token válido.

5. **Inserción del esqueleto JSON:** Para optimizar el rendimiento y evitar errores estructurales, la sintaxis estática del JSON (como `{`, `"name":`, `", "parameters": {` y `}`) es añadida directamente por mi código Python en lugar de ser generada por el LLM.

---

## Decisiones de diseño

- **Análisis dinámico del esquema:** En lugar de codificar reglas específicas para un conjunto concreto de funciones, el programa analiza dinámicamente las propiedades del esquema desde `functions_definition.json`. Esto garantiza la compatibilidad con cualquier nueva lista de funciones utilizada durante la corrección.

- **Filtrado de logits en Python puro:** Para mejorar la eficiencia y evitar dependencias externas pesadas, utilizo una estrategia de indexación selectiva:

```python
max(valid_token_ids, key=lambda idx: logits[idx])
```

Este enfoque es matemáticamente equivalente a enmascarar el resto de valores con $-\infty$, pero se ejecuta en microsegundos al evitar recorrer los 151.643 elementos del vocabulario.

- **Precálculo (Caching) al inicio:** Cargo y analizo el archivo `vocab.json` una única vez durante el arranque para prefiltrar y agrupar los IDs de tokens (por ejemplo, creando una lista de tokens exclusivamente numéricos). Durante la decodificación, simplemente consulto estas listas almacenadas en memoria.

- **Máquina de estados para los delimitadores JSON:** Utilizo los corchetes, llaves y comillas del JSON como transiciones de estado para detectar cuándo un valor de parámetro ha finalizado y cambiar inmediatamente de estado o terminar el bucle.

---

## Desafíos encontrados

### Desafío 1: El problema del carácter de espacio en BPE

**Problema:** Concatenar directamente las claves del vocabulario producía símbolos de bytes como `Ġ` en lugar de espacios y `Äł` en lugar de determinados caracteres especiales.

**Solución:** En lugar de concatenar directamente las cadenas del vocabulario, cuando necesito añadir la salida del LLM al *prompt* principal reemplazo `Ġ` por espacios.

### Desafío 2: Cuello de botella por recodificación

**Problema:** En las primeras pruebas, convertir los tokens a texto, añadirlos al *prompt* y volver a ejecutar `model.encode()` en cada iteración provocaba un enorme cuello de botella en la CPU, llegando a tardar aproximadamente un minuto por consulta.

**Solución:** Modifiqué el bucle para trabajar exclusivamente con IDs enteros (`list[int]`). Solo llamo a `model.encode()` una vez al inicio, añado directamente los IDs generados y ejecuto `model.decode()` únicamente al final. Esto redujo el tiempo de ejecución en más de un 90%.

### Desafío 3: Bucles infinitos en la generación de números

**Problema:** Los modelos pequeños pueden quedarse bloqueados generando cadenas infinitas del mismo dígito (por ejemplo `111111...`) porque el sesgo de repetición supera la puntuación del delimitador (coma o llave).

**Solución:** Añadí una comprobación de seguridad dentro de la restricción numérica. Si un número supera los 20 dígitos, el código fuerza el final estableciendo los logits de todos los dígitos a $-\infty$ y permitiendo únicamente el delimitador.

### Desafío 4: Prompts vacíos

**Problema:** Enviar un *prompt* vacío hacía que el modelo alucinara selecciones aleatorias de funciones.

**Solución:** Implementé validación mediante esquemas de Pydantic durante el análisis de entrada utilizando `min_length=1`. Los *prompts* vacíos se detectan y generan un error antes de llegar al LLM.

---

## Estrategia de pruebas

Validé el proyecto mediante las siguientes pruebas manuales y automáticas:

1. **Cumplimiento del esquema:** Verifiqué que el JSON generado coincide exactamente con la estructura definida en `functions_definition.json`.

2. **Validación de tipos:** Comprobé que los parámetros de tipo cadena aparecen correctamente entre comillas y que los parámetros numéricos no contienen letras.

3. **Entradas vacías:** Probé cadenas vacías para asegurar que la validación detecta el error y muestra mensajes claros sin provocar fallos del programa.

4. **Simulación del entorno de evaluación:** Ejecuté el conjunto completo de 11 *prompts* dentro del límite de cinco minutos para comprobar que el programa finaliza correctamente y genera el archivo de salida esperado.

---

## Ejemplo de uso

Dado el *prompt*:

*"¿Cuál es la suma de 2 y 3?"*

y la definición de la función `add_numbers` en `functions_definition.json`, el programa generará la siguiente salida en `output_file.json`:
 nbb
```json
{
  "prompt": "What is the sum of 2 and 3?",
  "name": "add_numbers",
  "parameters": {
    "a": 2,
    "b": 3
  }
}
```

Mi código es reutilizable y puede manejar cualquier definición de funciones y cualquier conjunto de *prompts*, siempre que sean válidos de acuerdo con los esquemas definidos.

El mecanismo de **Constrained Decoding** garantiza que la salida siempre será un JSON sintácticamente correcto, independientemente de la complejidad de las funciones o de los *prompts*.

Puedes clonar el repositorio y ejecutarlo con tus propias definiciones de funciones y *prompts* siguiendo las instrucciones descritas en la sección **Instrucciones**. Simplemente asegúrate de actualizar las rutas hacia tus archivos personalizados `functions_definition.json` y `function_calling_tests.json` al ejecutar el programa.

---
