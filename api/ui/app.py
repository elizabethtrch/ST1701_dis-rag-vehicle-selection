"""
Interfaz de usuario Streamlit para la API RAG de selección de vehículo.
Ejecutar con: streamlit run ui/app.py
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import requests
import streamlit as st

# ── Configuración de página ───────────────────────────────────
st.set_page_config(
    page_title="RAG Vehicle API",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS adicional ─────────────────────────────────────────────
st.markdown("""
<style>
.result-box {
    background: #f0f7ff;
    border-left: 4px solid #1f77b4;
    border-radius: 6px;
    padding: 1rem 1.2rem;
    margin: 0.5rem 0;
}
.alert-alta  { border-left-color: #d32f2f; background: #fff5f5; }
.alert-media { border-left-color: #f57c00; background: #fff8f0; }
.alert-baja  { border-left-color: #388e3c; background: #f5fff5; }
.cost-card {
    background: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 0.8rem 1rem;
    text-align: center;
}
</style>
""", unsafe_allow_html=True)

# ── Sidebar – configuración ───────────────────────────────────
with st.sidebar:
    st.title("⚙️ Configuración")

    api_url = st.text_input(
        "URL del API",
        value="http://localhost:8000",
        help="URL base del servidor FastAPI",
    )
    api_token = st.text_input(
        "Token de autenticación",
        value="dev-secret-token-change-in-prod",
        type="password",
    )

    st.divider()
    st.subheader("🤖 Proveedor LLM")

    LLM_OPTIONS = {
        "Anthropic (Claude)": "anthropic",
        "OpenAI (GPT)": "openai",
        "Google (Gemini)": "google",
        "Ollama (local)": "ollama",
    }
    llm_label = st.selectbox("Selecciona el LLM", list(LLM_OPTIONS.keys()))
    llm_provider = LLM_OPTIONS[llm_label]

    llm_info = {
        "anthropic": "🟣 Claude Opus / Sonnet – Anthropic API",
        "openai":    "🟢 GPT-4o / GPT-4o-mini – OpenAI API",
        "google":    "🔵 Gemini 1.5 Flash – Google AI API",
        "ollama":    "🟠 Llama 3.1 – ejecución local (Ollama)",
    }
    st.info(llm_info[llm_provider])

    st.divider()
    st.caption("El servidor debe estar ejecutándose con las API keys configuradas en `.env`")

# ── Título principal ──────────────────────────────────────────
st.title("🚛 Recomendación Inteligente de Vehículo")
st.markdown("Completa el formulario para obtener una recomendación de vehículo óptimo usando RAG.")

# ── Formulario principal ──────────────────────────────────────
with st.form("recomendacion_form"):

    col1, col2 = st.columns(2)

    # ── Pedido ────────────────────────────────────────────────
    with col1:
        st.subheader("📦 Pedido")
        pedido_id = st.text_input("ID del pedido", value="PED-001")
        fecha_entrega = st.date_input(
            "Fecha de entrega",
            value=date.today() + timedelta(days=3),
            min_value=date.today(),
        )
        prioridad = st.selectbox("Prioridad", ["alta", "media", "baja"], index=1)

    # ── Cliente ───────────────────────────────────────────────
    with col2:
        st.subheader("👤 Cliente")
        cliente_nombre = st.text_input("Nombre", value="Cooperativa Agro Sur")
        cliente_dir = st.text_input("Dirección", value="Calle 15 #42-10, Bogotá")
        c1, c2 = st.columns(2)
        with c1:
            cliente_lat = st.number_input(
                "Latitud", value=4.711, min_value=-4.5, max_value=13.0, format="%.4f"
            )
        with c2:
            cliente_lon = st.number_input(
                "Longitud", value=-74.072, min_value=-81.0, max_value=-66.0, format="%.4f"
            )

    st.divider()

    # ── Canal ─────────────────────────────────────────────────
    canal = st.selectbox(
        "📡 Canal de venta",
        ["mayorista", "minorista", "exportacion", "institucional"],
        index=0,
    )

    st.divider()

    # ── Productos ─────────────────────────────────────────────
    st.subheader("🌾 Productos")
    st.caption("Define los productos a transportar (mínimo 1)")

    num_productos = st.number_input("Número de productos", min_value=1, max_value=10, value=2, step=1)

    productos_data = []
    prod_cols = st.columns(3)
    DEFAULTS_PROD = [
        ("Aguacate Hass", 500.0, "kg"),
        ("Plátano", 300.0, "kg"),
        ("Tomate", 200.0, "kg"),
    ]
    for i in range(int(num_productos)):
        default = DEFAULTS_PROD[i] if i < len(DEFAULTS_PROD) else (f"Producto {i+1}", 100.0, "kg")
        with st.expander(f"Producto {i+1}", expanded=(i == 0)):
            pc1, pc2, pc3 = st.columns([3, 2, 2])
            with pc1:
                pnombre = st.text_input("Nombre", value=default[0], key=f"pnombre_{i}")
            with pc2:
                pcantidad = st.number_input("Cantidad", value=default[1], min_value=0.1, key=f"pcant_{i}")
            with pc3:
                punidad = st.selectbox("Unidad", ["kg", "ton", "unidades"], key=f"punidad_{i}",
                                       index=["kg", "ton", "unidades"].index(default[2]))
            productos_data.append({"nombre": pnombre, "cantidad": pcantidad, "unidad": punidad})

    st.divider()

    # ── Flota disponible ──────────────────────────────────────
    st.subheader("🚐 Flota disponible")
    st.caption("Define los vehículos disponibles para el despacho (mínimo 1)")

    num_vehiculos = st.number_input("Número de vehículos", min_value=1, max_value=10, value=3, step=1)

    DEFAULTS_VEH = [
        ("VH-001", "TERRESTRE", 2000.0, False, "ABC-123"),
        ("VH-002", "TERRESTRE", 5000.0, True,  "DEF-456"),
        ("VH-003", "AEREO",     800.0,  False, "AIR-001"),
        ("VH-004", "ACUATICO",  3000.0, False, "ACU-001"),
    ]
    vehiculos_data = []
    for i in range(int(num_vehiculos)):
        default = DEFAULTS_VEH[i] if i < len(DEFAULTS_VEH) else (f"VH-{i+10:03}", "TERRESTRE", 1000.0, False, None)
        with st.expander(f"Vehículo {i+1}", expanded=(i == 0)):
            vc1, vc2, vc3, vc4, vc5 = st.columns([2, 2, 2, 1, 2])
            with vc1:
                vid = st.text_input("ID", value=default[0], key=f"vid_{i}")
            with vc2:
                vtipo = st.selectbox("Tipo", ["TERRESTRE", "AEREO", "ACUATICO"],
                                     index=["TERRESTRE", "AEREO", "ACUATICO"].index(default[1]),
                                     key=f"vtipo_{i}")
            with vc3:
                vcap = st.number_input("Capacidad (kg)", value=default[2], min_value=1.0, key=f"vcap_{i}")
            with vc4:
                vref = st.checkbox("Refrigerado", value=default[3], key=f"vref_{i}")
            with vc5:
                vmat = st.text_input("Matrícula", value=default[4] or "", key=f"vmat_{i}")
            vehiculos_data.append({
                "id": vid,
                "tipo": vtipo,
                "capacidad_kg": vcap,
                "refrigerado": vref,
                "matricula": vmat if vmat else None,
            })

    st.divider()

    submitted = st.form_submit_button("🔍 Obtener recomendación", type="primary", use_container_width=True)

# ── Lógica de envío ───────────────────────────────────────────
if submitted:
    payload = {
        "pedido": {
            "identificador": pedido_id,
            "fecha_entrega": fecha_entrega.isoformat(),
            "prioridad": prioridad,
        },
        "productos": productos_data,
        "cliente": {
            "nombre": cliente_nombre,
            "direccion": cliente_dir,
            "latitud": cliente_lat,
            "longitud": cliente_lon,
        },
        "canal": canal,
        "flota_disponible": vehiculos_data,
        "llm_provider": llm_provider,
    }

    # Validación rápida de IDs únicos
    ids = [v["id"] for v in vehiculos_data]
    if len(ids) != len(set(ids)):
        st.error("❌ Los IDs de la flota deben ser únicos.")
        st.stop()

    with st.spinner(f"Consultando el API usando **{llm_label}**..."):
        try:
            resp = requests.post(
                f"{api_url}/api/v1/vehicle-recommendation",
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_token}",
                    "Content-Type": "application/json",
                },
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.ConnectionError:
            st.error(f"❌ No se pudo conectar al servidor en `{api_url}`. Verifica que el API esté corriendo.")
            st.stop()
        except requests.exceptions.HTTPError as e:
            st.error(f"❌ Error HTTP {resp.status_code}: {resp.text}")
            st.stop()
        except Exception as e:
            st.error(f"❌ Error inesperado: {e}")
            st.stop()

    # ── Mostrar resultados ────────────────────────────────────
    st.success(f"✅ Recomendación generada con **{llm_label}** · Trace ID: `{data['trace_id']}`")

    st.divider()
    col_a, col_b = st.columns([3, 2])

    with col_a:
        # Vehículo recomendado
        v = data["vehiculo_recomendado"]
        st.subheader("🏆 Vehículo recomendado")
        st.markdown(f"""
<div class="result-box">
<h3 style="margin:0">ID: <code>{v['id']}</code></h3>
<p style="margin:4px 0">Tipo: <strong>{v['tipo']}</strong> &nbsp;|&nbsp; Matrícula: <strong>{v.get('matricula') or '—'}</strong></p>
</div>
""", unsafe_allow_html=True)

        # Justificación
        st.subheader("📋 Justificación")
        st.markdown(data["justificacion"])

        # Alternativas
        if data.get("alternativas"):
            st.subheader("🔄 Alternativas")
            for alt in data["alternativas"]:
                st.markdown(f"- **{alt['id']}**: {alt['motivo']}")

        # Alertas
        if data.get("alertas"):
            st.subheader("⚠️ Alertas")
            for alerta in data["alertas"]:
                nivel = alerta["nivel"]
                icon = {"alta": "🔴", "media": "🟡", "baja": "🟢"}.get(nivel, "⚪")
                st.markdown(
                    f'<div class="result-box alert-{nivel}">{icon} <strong>{nivel.upper()}</strong>: {alerta["mensaje"]}</div>',
                    unsafe_allow_html=True,
                )

    with col_b:
        # Métricas
        st.subheader("📊 Métricas")
        st.metric("Costo estimado (COP)", f"${data['costo_estimado_cop']:,.0f}")
        st.metric("Tiempo estimado", f"{data['tiempo_estimado_min']} min")

        # Desglose de costos
        st.subheader("💰 Desglose de costos")
        d = data["desglose_costo"]
        items = [
            ("Combustible",   d["combustible_cop"]),
            ("Peajes",        d["peajes_cop"]),
            ("Viáticos",      d["viaticos_cop"]),
            ("Seguro",        d["seguro_cop"]),
            ("Imprevistos",   d["imprevistos_cop"]),
        ]
        for label, valor in items:
            cols = st.columns([3, 2])
            cols[0].markdown(label)
            cols[1].markdown(f"**${valor:,.0f}**")
        st.markdown(f"**Total: ${d['total_cop']:,.0f}**")

    # JSON raw colapsable
    with st.expander("🔧 Ver JSON completo de la respuesta"):
        st.json(data)

    with st.expander("🔧 Ver JSON del request enviado"):
        st.json(payload)
