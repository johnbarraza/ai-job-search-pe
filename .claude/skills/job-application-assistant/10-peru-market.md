---
framework_version: 1.3.0
---

# Mercado laboral peruano (fork Perú)

Reglas y datos del mercado peruano que aplican **además** del framework general
(`04-job-evaluation.md`, `05-cv-templates.md`, `06-cover-letter-templates.md`). Cifras
verificadas al **2026-10-15**; las que cambian cada año (RMV, UIT, comisiones AFP) viven
también en `tools/pe_sueldo.py` (`PARAMS`). Si una cifra de aquí y una del código no
coinciden, manda la más reciente con fuente.

---

## 1. Dónde buscar y cómo cubre cada portal este repo

| Portal | Qué cubre | Cómo lo usa el repo |
|---|---|---|
| **LinkedIn Jobs** | Banca, consultoría, multinacionales, roles junior y prácticas corporativas | CLI `linkedin-search` con `-l "Lima, Peru"` |
| **Bumeran Perú** | Empresas grandes y medianas, analistas, practicantes, entrada | CLI `bumeran-search` (filtros de región, distrito, modalidad, nivel y antigüedad del lado del servidor) |
| **Computrabajo Perú** | El mayor volumen; todos los sectores y regiones; publica sueldo a veces | CLI `computrabajo-search` (distritos de Lima/Callao resueltos solos) |
| **Get on Board** | Datos, analytics, tecnología, startups; remotos abiertos a Perú | CLI `getonboard-search -l Peru` |
| **Bolsa de la universidad** (p. ej. Red Alumni UP) | Prácticas dirigidas a estudiantes/egresados de esa universidad | Requiere login: alertas por correo + `/apply`, o `jev-search --site url --url <bolsa>` tras iniciar sesión a mano una vez en su perfil de Chrome |
| **Talento Perú (SERVIR)** | Todo el empleo y las prácticas del Estado (CAS, 728, servicio civil) | App con estado y WAF, sin URLs estables: `jev-search --site talentoperu` (navegador real, opcional y de pago) o búsqueda web `site:` |
| **Prácticas.pe** | Agregador de convocatorias de prácticas, sobre todo del Estado | Búsqueda web `site:practicas.pe` |
| **Empleos Perú (MTPE)** | Bolsa oficial del Ministerio de Trabajo | Búsqueda web; volumen bajo para perfiles profesionales |
| **Laborum Perú** | Corporativo y administrativo | Otra plataforma (no Navent): búsqueda web `site:laborum.pe` |
| **Indeed Perú** | Agregador | `robots.txt` bloquea `/jobs/PE/` y la búsqueda está protegida: solo búsqueda web o alertas por correo |

Notas:
- **Agencias de selección.** Muchas ofertas en Bumeran/Computrabajo las publica una
  consultora (ManpowerGroup, Adecco, Randstad, Michael Page…) para "una importante empresa
  del sector". El cliente a veces se deduce de la descripción ("el banco más grande del
  Perú"); no lo afirmes como hecho en la carta salvo que la oferta lo nombre.
- **Herramientas de terceros.** Bibliotecas como JobSpy raspan Indeed y LinkedIn desde
  Python, pero dependen de endpoints internos que esos sitios no autorizan; este repo no las
  integra. Los flujos n8n de alertas (Telegram, Notion) duplican lo que ya hacen `/scrape`,
  `/rank` y `/notion-sync` aquí.
- **LinkedIn con sesión iniciada (Agent-Reach / linkedin-mcp-server): no integrado.**
  Agent-Reach delega LinkedIn en `linkedin-mcp-server`, que maneja **tu cuenta** con un
  navegador automatizado e importa la cookie de sesión de tu Chrome. Da búsqueda de empleos,
  detalle y "Easy Apply", pero automatizar la cuenta va contra el acuerdo de usuario de
  LinkedIn, y el propio README de Agent-Reach advierte riesgo de bloqueo y recomienda una
  cuenta secundaria. En una búsqueda de empleo tu cuenta principal vale más que lo que
  añade. Para ofertas, `linkedin-search` (páginas públicas, sin login) ya cubre búsqueda y
  descripción completa. Si aun así decides usarlo, es una decisión tuya y fuera del repo:
  `claude mcp add linkedin -- uvx mcp-server-linkedin@latest`, preferiblemente con una cuenta
  secundaria.
- **jev-search** (navegador real con jev-browse): para tableros que no se pueden leer con
  una petición simple. Es opcional y de pago, pasa por el control de robots.txt y se detiene
  ante cualquier CAPTCHA. Detalles en `.agents/skills/jev-search/SKILL.md`.

## 2. Sector público

- Las entidades deben difundir sus convocatorias en **Talento Perú** (SERVIR) y en su web
  institucional por al menos **10 días hábiles**: el plazo es corto y fijo. Cuando `/rank`
  o `/apply` vean una convocatoria pública, marca la fecha de cierre como urgente.
- Regímenes que vas a ver: **CAS** (D. Leg. 1057, el más común; hoy con plazos
  determinados o indeterminados según la convocatoria), **728** (régimen privado en
  entidades como BCRP, SBS, Indecopi), **Servicio Civil** (Ley 30057).
- La postulación pública es **formal y documentada**: formato de CV de la entidad o "CV
  documentado", declaraciones juradas, anexos firmados, y una evaluación curricular por
  puntaje seguida de entrevista. Un requisito no acreditado con documento descalifica,
  aunque se cumpla. En `/apply`, para una convocatoria pública:
  1. Lista cada requisito mínimo del perfil del puesto (formación, experiencia general,
     experiencia específica, cursos/diplomados con horas, conocimientos) y marca con qué
     documento se acredita cada uno.
  2. La experiencia se cuenta desde el egreso (o según indique la convocatoria) y por
     tiempo exacto: calcula meses por puesto en vez de redondear.
  3. No redactes carta de presentación salvo que la bases la pidan.
- **Prácticas en el Estado** se rigen por el D. Leg. 1401 (no por la Ley 28518) y también se
  publican en Talento Perú. Las prácticas profesionales en el sector público solo pueden
  hacerse dentro de los 12 meses siguientes a obtener la condición de egresado.
- **INEI (censos, encuestas, trabajo de campo).** Su página de convocatorias
  (`inei.gob.pe/usuarios/convocatoria-de-personal/`) carga la lista con JavaScript, así que
  una lectura simple la ve vacía. La misma página la pide a
  `/usuarios/convocatoria-de-personal/datos-cas/<página>/<cantidad>/?tipo=C&year=<año>`
  (`tipo` = `C` CAS, `PPRE`/`PPRO` prácticas) y a `.../datos-locador/<página>/<cantidad>/`
  (locaciones de servicio de campo: encuestadores, supervisores, aplicadores; responde JSON
  con `cargo`, `periodo_inicio`, `peridodo_fin` y `estado`, donde `1` es abierto). Ahí aparecen
  primero las convocatorias de encuestas (ENAHO, ENDES, ENCAL) y evaluaciones, que los
  agregadores replican tarde.

## 3. CV para el mercado peruano

El CV va en **español** salvo que la oferta esté en inglés o sea de una multinacional que
recluta en inglés. Además de `05-cv-templates.md`:

- **Datos personales:** nombre, celular con formato peruano (`+51 9XX XXX XXX`), correo,
  LinkedIn, y **distrito** de residencia (no la dirección exacta). No incluyas DNI, estado
  civil, fecha de nacimiento ni foto salvo que la oferta los pida; la foto es habitual en
  Perú pero no obligatoria, y se omite para multinacionales y postulaciones en inglés.
- **Formación:** universidad, carrera y **ciclo actual** ("8.º ciclo") o **fecha de
  egreso** ("Egresado, 2026-I"). Muchas ofertas filtran por ciclo o por fecha de egreso
  ("desde 6.º ciclo", "egreso 2027-II"): ponlo donde un reclutador lo vea en 5 segundos.
- **Mérito académico:** "Décimo superior", "Quinto superior" o "Tercio superior" es un
  filtro explícito en banca, consultoría, BCRP, MEF y SBS. Inclúyelo **solo si consta**
  en el perfil del candidato, con el periodo ("Quinto superior, 2024-II").
- **Grados:** distingue *estudiante*, *egresado*, *bachiller*, *titulado* y
  *colegiado*: en Perú son estados distintos y las ofertas los piden por nombre. El grado se
  puede verificar en el registro de grados de SUNEDU, así que nunca adelantes uno que aún no
  se tiene ("Bachiller en trámite" solo si es cierto).
- **Herramientas con nivel:** las ofertas peruanas piden niveles explícitos ("Excel
  avanzado", "Power BI intermedio", "SQL básico"). Declara el nivel real; si el perfil dice
  "intermedio", el CV no dice "avanzado".
- **Idiomas:** nivel y, si existe, certificado o institución (ICPNA, Británico, TOEFL,
  Cambridge).
- **Referencias:** es costumbre cerrar con "Referencias disponibles a solicitud" o con 1–2
  referencias laborales (nombre, cargo, empresa, contacto) **solo** con su permiso. Esto
  reemplaza la línea de referencias por defecto del template (ver `05-cv-templates.md`).
- **Extensión: 1 página** (una sola cara). Es lo más común en Perú y es el default de este
  fork (`CV length: 1 page` en CLAUDE.md, que `/apply` verifica con `verify_pdf.py --pages 1`).
  Solo se hace de 2 páginas si el candidato lo pide y cambia esa línea a `2 pages`. El CV
  maestro (`cv/main_example.tex`) puede ser más largo: es el inventario del que se recorta.

## 4. Formularios y pretensión salarial

- Bumeran, Computrabajo y los portales de empresas preguntan casi siempre la
  **pretensión salarial** ("remuneración bruta mensual"). Antes de responder:
  1. `python tools/myworkin_salaries.py "<empresa>"` para rangos autodeclarados de esa
     empresa (MyWorkIn; a menudo 1–2 aportes por puesto: es una referencia, no una escala).
  2. `python tools/pe_sueldo.py <monto> --comparar` para ver cuánto vale el monto según el
     régimen (planilla general, pequeña empresa, microempresa, recibo por honorarios).
  3. Responde con un monto **bruto mensual** coherente con ambos y redondeado ("S/ 3,500"),
     o con un rango corto si el formulario lo permite.
- Si la oferta no aclara el régimen, pregúntalo en la entrevista: "S/ 4,000 en planilla"
  vale bastante más por año que "S/ 4,000 por recibo por honorarios" (ver sección 6).

## 5. Prácticas (Ley 28518, sector privado)

Verificado contra el resumen de la Red Alumni UP de la Ley 28518:

- **Preprofesionales** (estudiantes): máximo **6 h diarias o 30 h semanales**.
  **Profesionales** (egresados): máximo **8 h diarias o 48 h semanales**.
- **Subvención** mensual no menor a **una RMV (S/ 1,230 desde el 1/10/2026)** cuando se
  cumple la jornada máxima; proporcional si la jornada es menor.
- **Media subvención adicional** cada seis meses de duración continua.
- **15 días de descanso subvencionado** si el convenio dura más de 12 meses.
- **Seguro** de enfermedad y accidentes a cargo de la empresa, por una de dos vías:
  - **Seguro FOLA** (Formación Laboral): póliza privada, la más común para practicantes
    (por ejemplo AMI FOLA de Rímac; también la ofrecen otras aseguradoras). Atiende en la red
    de clínicas de la aseguradora, con copagos según el plan.
  - **EsSalud**: algunas empresas afilian al practicante a EsSalud en lugar del FOLA.
  - En ambos casos la cobertura mínima legal es de **14 subvenciones mensuales por
    enfermedad y 30 por accidente**. Si la oferta no dice cuál, pregúntalo: cambia la red
    de atención y los copagos. Ninguna de las dos se descuenta de la subvención.
- Afiliación pensionaria **facultativa** (no hay descuento obligatorio de AFP/ONP).
- El convenio es tripartito (empresa, practicante, universidad) e incluye un plan de
  aprendizaje. **Política UP:** una vez aprobada la plaza por Red Alumni, el estudiante no
  puede dejarla ni cambiarla salvo razones acreditadas, y una renuncia unilateral puede
  afectar procesos futuros. Aceptar una práctica es un compromiso: en `/apply` y en la
  negociación de ofertas, compara las alternativas abiertas **antes** de firmar.
- La duración máxima de las prácticas profesionales tiene versiones distintas según la
  fuente (12 meses en el material UP; hasta 24 meses según la Ley 31396). Verifica en la
  norma vigente antes de afirmarlo en una carta o entrevista.

## 6. Cómo leer una oferta de sueldo en Perú

`tools/pe_sueldo.py` hace todas estas cuentas. Lo esencial:

| Concepto | Régimen general (planilla) | Pequeña empresa (REMYPE) | Microempresa (REMYPE) | Recibo por honorarios |
|---|---|---|---|---|
| Sueldos al año | 12 + 2 gratificaciones (julio, diciembre) | 12 + 2 medias gratificaciones | 12 | 12 recibos |
| Bonificación extraordinaria | 9% de cada gratificación (Ley 30334) | 9% de cada media gratificación | — | — |
| CTS | ≈ 1 sueldo (+1/6 de gratificación) al año, depósitos en mayo y noviembre | 15 remuneraciones diarias al año | — | — |
| Vacaciones | 30 días | 15 días | 15 días | — |
| Salud | EsSalud 9% (lo paga el empleador) | EsSalud | EsSalud o SIS | Por cuenta propia |
| Pensión (descuento) | AFP ≈ 10% + 1.37% + comisión, u ONP 13% | igual | igual | sin descuento obligatorio |
| Impuesto | 5ta categoría: 8–30% sobre lo que excede 7 UIT | igual | igual | 4ta: retención 8% si el recibo supera S/ 1,500; renta anual con 20% deducible |

- **UIT 2026:** S/ 5,500 (D.S. 301-2025-EF). **RMV:** S/ 1,230 desde el 1/10/2026
  (D.S. 015-2026-TR), con un segundo tramo a S/ 1,300 pendiente de decreto en el primer
  semestre de 2027.
- **Asignación familiar:** 10% de la RMV con hijos menores (planilla).
- **Utilidades** (D. Leg. 892): en empresas con más de 20 trabajadores que generan renta de
  tercera categoría, entre 5% y 10% de la renta anual según sector. Es variable; no la sumes
  al valor de una oferta salvo que la empresa informe un histórico.
- **REMYPE:** los beneficios reducidos solo valen si la empresa está inscrita en el
  REMYPE; si no, corresponde el régimen general.
- **Recibo por honorarios para un trabajo con horario, jefe y exclusividad** es una
  relación laboral encubierta. Señálalo como riesgo en la evaluación de fit.

## 7. Modalidad: presencial, híbrida o remota

Cada CLI de portal peruano devuelve un campo `modality` normalizado (`presencial`,
`híbrido`, `remoto` o `no declarado`). En Computrabajo, una oferta sin etiqueta de modalidad es
presencial (el sitio solo etiqueta remotas e híbridas); en LinkedIn la modalidad solo se
conoce si la búsqueda usó `--remote`. `/scrape`, `/rank` y `/apply` la comparan con la línea
`Work mode preference` del perfil (`04-job-evaluation.md`, sección 4):

- Una modalidad que el candidato descarta baja el fit o lo veta, según cómo esté escrita la
  preferencia.
- "No declarado" no se adivina: queda como FLAG y como pregunta para el reclutador
  ("¿cuántos días presenciales y en qué sede?").
- En prácticas, la modalidad y el horario (turno mañana/tarde, 6 horas) deben calzar con el
  horario de clases: anótalo en la evaluación.

### Nivel del puesto

Cada resultado trae también `level`, clasificado desde el título (y, si el título no dice
nada, desde la etiqueta de experiencia del portal):

| Nivel | Señales en el título | Para quién |
|---|---|---|
| práctica preprofesional | "practicante preprofesional", "prácticas pre profesionales" | estudiante (a menudo "desde 6.º ciclo") |
| práctica profesional | "practicante profesional", "prácticas profesionales" | egresado |
| práctica | "practicante", "intern", "summer intern" (sin decir cuál) | revisar requisitos |
| pasantía | "pasante", "pasantía" | estudiante o egresado |
| programa de extensión | "programa de extensión", "PEU", "curso de extensión", "programa de especialización" | últimos ciclos / egresados (ver sección 9) |
| trainee | "trainee", "programa de talento", "jóvenes profesionales" | recién egresado |
| asistente de investigación | "asistente de investigación", "research assistant" | estudiante o egresado |
| asistente / analista / asociado | "asistente", "auxiliar" / "analista" / "asociado", "associate" | junior según requisitos |
| junior, semi senior, senior | "junior", "jr" / "semi senior", "ssr" / "senior", "sr" | por experiencia |
| jefatura | "jefe", "gerente", "coordinador", "supervisor", "lead", "manager" | experimentado |

Un título con señal de seniority manda sobre el rol: "Analista Senior" es `senior`, no
`analista`. `/scrape`, `/rank` y `/apply` comparan el nivel con la línea `Target level` del
perfil (`04-job-evaluation.md`, sección 2).

## 8. Lima: ubicación y traslado

El tiempo de traslado en Lima pesa más que la distancia. Para el criterio de ubicación de
`04-job-evaluation.md`, el perfil debe listar distritos aceptables, no solo "Lima".

- **Polos de oficinas:** San Isidro (centro financiero: bancos, consultoras, BCRP, SBS),
  Miraflores, Santiago de Surco (Chacarilla, Jockey Plaza), La Molina, San Borja, Magdalena
  y Jesús María; **Cercado de Lima** concentra entidades públicas (ministerios, MEF);
  **Callao**, Lurín y Ate concentran logística e industria.
- Los CLIs aceptan distritos directamente: `computrabajo-search -l "San Isidro"`,
  `bumeran-search -l "SJL"`.
- Para ofertas híbridas, el número de días presenciales cambia mucho el costo real del
  traslado: si la oferta no lo dice, es una pregunta para la entrevista.

## 9. Programas de extensión universitaria y cursos de extensión

Los reguladores y otras entidades públicas (OSINERGMIN, OSIPTEL, SUNASS, OSITRAN, INDECOPI,
SBS, ProInversión, SMV) y el BCRP ofrecen cada año programas de extensión (PEU), cursos de
extensión o programas de especialización: becas integrales de formación, normalmente de
enero a marzo, con examen de admisión. Los mejores puestos suelen recibir prácticas o
entrevistas en la entidad, así que para un estudiante de últimos ciclos o un recién egresado
de Economía, Derecho o Ingeniería son una de las vías de entrada más directas al sector
público y regulatorio.

- **Calendario típico:** inscripciones entre septiembre y noviembre, examen en noviembre o
  diciembre, clases de enero a marzo. Las ventanas no se mueven por la búsqueda de empleo:
  hay que vigilarlas aparte.
- **Requisitos frecuentes:** últimos tres ciclos o egresado del año (OSINERGMIN pide egresar en
  2026 para la edición 2027), **tercio superior** (SMV, SBS), inglés (BCRP avanzado, SMV
  intermedio) y disponibilidad exclusiva durante el programa.
- **Registro verificado:** `data/peru/programas_extension.json` guarda cada programa con su
  fuente, su estado (`abierta`, `por_confirmar`, `cerrada`) y la fecha de verificación.
  `python tools/pe_programas.py` lista los abiertos por cercanía del cierre (🔥 a 7 días o
  menos) y marca para re-verificar lo que tenga más de 21 días. `/scrape` los muestra en su
  propia tabla (Paso 1d).
- **Fechas sin confirmar no se presentan como hechos.** Si una convocatoria solo aparece en
  una fuente secundaria, queda `por_confirmar` hasta verla en la página oficial.
- **Postulación:** cada programa tiene su formulario y documentos (constancia de tercio
  superior, constancia de egreso o de matrícula, a veces carta de presentación o CV). `/apply`
  puede preparar el CV de una página y la carta si las bases los piden.

## 10. Frescura de la oferta y ghost jobs

En Perú la mayoría de procesos privados arma su terna en los **primeros días** del aviso, y
muchos avisos siguen publicados cuando la plaza ya se cubrió, cuando la consultora junta un
pool permanente de CVs o cuando nadie se acordó de bajarlos ("ghost jobs"). La fecha que
muestra cada portal **no es la edad del aviso**:

| Portal | Qué fecha muestra la búsqueda | Dónde está la fecha real | Otras señales en `detail` |
|---|---|---|---|
| Computrabajo | La última **renovación**: el empleador "actualiza" el aviso para volver arriba. En una búsqueda real de octubre de 2026, los 20 avisos de la página parecían de "hace horas" | JSON-LD de la página: `date` (= `datePosted`) | `updated` (renovación), `validThrough` (vencimiento del portal: publicación + 60 días) |
| Bumeran | `fechaPublicacion`, que el empleador puede reiniciar al republicar | Los ids son secuenciales: un id muy bajo para su fecha delata un aviso antiguo | `updated`, `validThrough` (fin del plan), `status`, `vacancies`, `contractType` (a veces "Temporal" aunque el texto no lo diga) |
| LinkedIn | La fecha del último *repost* | Ids secuenciales, igual que Bumeran | `postedAgo`, `reposted`, `applicants` ("189 applicants"), `isActive` |

Reglas:
- **Edad desde la publicación original**, nunca desde la renovación. ≤ 7 días: *fresca*
  (postula ya); 8 a 21: *en curso*; 22 a 45: *vieja*; más de 45: *muy vieja*.
- **El vencimiento del portal no es una fecha de cierre.** `validThrough` sale del plan
  contratado (60 días en Computrabajo, ~90 en Bumeran); solo es una fecha límite real cuando
  la oferta la escribe o en una convocatoria pública (cronograma de las bases). Nunca la
  guardes como `deadline`.
- **Señales de ghost job:** aviso cerrado o vencido en el portal; más de 45 días de edad;
  republicado (LinkedIn *reposted* o id antiguo para su fecha); mismo título y empresa
  publicados varias veces; más de 200 postulantes en LinkedIn. Una renovación sola **no**
  sube el riesgo: también puede significar que siguen buscando.
- **Con riesgo medio o alto, confirma antes de invertir tiempo:** escribe al reclutador o a la
  empresa, o busca en LinkedIn si ya contrataron a alguien para ese puesto. Una carta a medida
  va primero a las ofertas frescas.
- **Herramienta:** guarda el `detail --format json` de cada oferta preseleccionada y corre
  `python tools/pe_frescura.py <detalles.json> --calibrar <búsquedas.json> job_scraper/seen_jobs.json`.
  Ordena por riesgo, explica cada señal y estima la fecha de creación de los ids de Bumeran y
  LinkedIn con los pares (id, fecha) de la propia búsqueda. Es una señal para priorizar, no un
  juicio sobre el empleador.

## Fuentes (consultadas 2026-10-15)

- RMV: [El Peruano, D.S. 015-2026-TR](https://busquedas.elperuano.pe/dispositivo/EX/2559163-1);
  [El Peruano, nota del 1/10/2026](https://elperuano.pe/noticia/305879-desde-hoy-rige-la-nueva-rmv-sueldo-minimo-sube-a-s-1230-y-cambia-otros-conceptos-laborales)
- UIT 2026: [EY Perú](https://www.ey.com/es_pe/insights/tax/nuevo-valor-uit-como-impacta)
- Renta de trabajo (4ta y 5ta): [SUNAT, guía cuarta y quinta](https://renta.sunat.gob.pe/sites/default/files/archivos/CUARTA_QUINTA_0.pdf);
  [SUNAT, deducción adicional](https://renta.sunat.gob.pe/personas/deduccion-adicional-para-rentas-de-trabajo)
- Suspensión de retenciones 4ta 2026: [Infobae](https://www.infobae.com/peru/2026/06/21/suspension-de-cuarta-categoria-quienes-pueden-pedirla-y-como-hacerlo/)
- AFP (aporte, prima, comisiones): [SBS, comisiones y primas](https://www.sbs.gob.pe/app/spp/empleadores/comisiones_spp/Paginas/comision_prima.aspx)
- Prácticas (Ley 28518): [Red Alumni UP, condiciones de prácticas preprofesionales](https://alumni.up.edu.pe/wp-content/uploads/Condiciones-practicas-preprofesionales.pdf);
  [Rímac, manual del afiliado AMI FOLA](https://imagescdn.rimac.com/blt544733979a698c77/680a772fb5716ce6643628e4/Manual_de_Afiliado_AMI_FOLA.pdf);
  [Gestión, seguro para practicantes](https://gestion.pe/economia/management-empleo/seguro-para-practicantes-a-cuanto-asciende-la-cobertura-en-caso-de-enfermedad-o-accidente-fedu-estudiantes-empleo-mapfre-noticia/);
  [D. Leg. 1401 (PUCP)](https://facultad-derecho.pucp.edu.pe/wp-content/uploads/2022/08/decreto-legislativo-1401.pdf)
- Talento Perú / SERVIR: [LP Derecho](https://lpderecho.pe/portal-publicara-ofertas-empleos-practicas-instituciones-publicas)
- REMYPE: [LP Derecho, régimen REMYPE laboral](https://lpderecho.pe/regimen-remype-laboral)
- Sueldos por empresa: [MyWorkIn](https://www.myworkin.ai/salaries)
- Programas de extensión: fuentes por programa en `data/peru/programas_extension.json` (campo `sources`).
