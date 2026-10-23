
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
import base64
import hmac
import json
import math
import os

import psycopg2


PASTA = Path(__file__).resolve().parent
DATABASE_URL = os.environ.get("DATABASE_URL")
ACCESS_PASSWORD = os.environ.get("ACCESS_PASSWORD")


def conectar():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL não configurada")

    return psycopg2.connect(
        DATABASE_URL,
        sslmode="require",
        connect_timeout=10
    )


def inicializar_banco():
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS coordenadas (
                    id BIGSERIAL PRIMARY KEY,
                    latitude DOUBLE PRECISION NOT NULL,
                    longitude DOUBLE PRECISION NOT NULL,
                    data_hora TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)


class Handler(SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            directory=str(PASTA),
            **kwargs
        )

    def responder_json(self, status, dados):
        resposta = json.dumps(dados).encode("utf-8")

        self.send_response(status)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(resposta)))
        self.end_headers()
        self.wfile.write(resposta)

    def autorizado(self):
        if not ACCESS_PASSWORD:
            self.send_error(
                503,
                "Acesso não configurado no Render"
            )
            return False

        cabecalho = self.headers.get("Authorization", "")

        try:
            esquema, token = cabecalho.split(" ", 1)

            credenciais = base64.b64decode(
                token,
                validate=True
            ).decode("utf-8")

            usuario, senha = credenciais.split(":", 1)

            valido = (
                esquema.lower() == "basic"
                and usuario == "admin"
                and hmac.compare_digest(
                    senha,
                    ACCESS_PASSWORD
                )
            )

        except (ValueError, UnicodeDecodeError):
            valido = False

        if not valido:
            self.send_response(401)
            self.send_header(
                "WWW-Authenticate",
                'Basic realm="Consulta de coordenadas", charset="UTF-8"'
            )
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return False

        return True

    def do_GET(self):
        caminho = urlparse(self.path).path

        # Página inicial: serve index.html ou outros arquivos estáticos.
        if caminho == "/":
            return super().do_GET()

        # Consulta privada das coordenadas.
        if caminho != "/coordenadas":
            self.send_error(404, "Página não encontrada")
            return

        if not self.autorizado():
            return

        try:
            with conectar() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, latitude, longitude, data_hora
                        FROM coordenadas
                        ORDER BY id DESC
                        LIMIT 500
                    """)
                    registros = cur.fetchall()

            linhas = []

            for ident, lat, lon, data_hora in registros:
                mapa = (
                    "https://www.google.com/maps?q="
                    f"{lat},{lon}"
                )

                data = data_hora.strftime(
                    "%d/%m/%Y %H:%M:%S UTC"
                )

                linhas.append(f"""
                    <tr>
                        <td>{ident}</td>
                        <td>{lat}</td>
                        <td>{lon}</td>
                        <td>{data}</td>
                        <td>
                            <a href="{mapa}"
                               target="_blank"
                               rel="noopener noreferrer">
                               Abrir mapa
                            </a>
                        </td>
                    </tr>
                """)

            tabela = "\n".join(linhas)

            if not tabela:
                tabela = """
                    <tr>
                        <td colspan="5">
                            Nenhuma coordenada recebida.
                        </td>
                    </tr>
                """

            pagina = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Minhas coordenadas</title>
<style>
body {{
    font-family: Arial, sans-serif;
    margin: 24px;
    background: #f5f6f8;
    color: #222;
}}
.container {{
    max-width: 1100px;
    margin: auto;
    background: white;
    padding: 20px;
    border-radius: 10px;
}}
table {{
    border-collapse: collapse;
    width: 100%;
    background: white;
}}
th, td {{
    border: 1px solid #ddd;
    padding: 10px;
    text-align: left;
}}
th {{
    background: #eee;
}}
a {{
    color: #075dc7;
}}
.aviso {{
    color: #555;
}}
@media (max-width: 700px) {{
    .container {{
        padding: 10px;
        overflow-x: auto;
    }}
    table {{
        min-width: 650px;
    }}
}}
</style>
</head>
<body>
<div class="container">
    <h1>Coordenadas recebidas</h1>
    <p>Mostrando até 500 registros, do mais recente ao mais antigo.</p>
    <p class="aviso">Horários apresentados em UTC.</p>

    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Latitude</th>
                <th>Longitude</th>
                <th>Data e hora</th>
                <th>Localização</th>
            </tr>
        </thead>
        <tbody>
            {tabela}
        </tbody>
    </table>
</div>
</body>
</html>"""

            resposta = pagina.encode("utf-8")

            self.send_response(200)
            self.send_header(
                "Content-Type",
                "text/html; charset=utf-8"
            )
            self.send_header("Cache-Control", "no-store")
            self.send_header(
                "Content-Length",
                str(len(resposta))
            )
            self.end_headers()
            self.wfile.write(resposta)

        except Exception:
            print(
                "Erro ao consultar coordenadas:",
                flush=True
            )
            self.send_error(
                500,
                "Erro ao consultar as coordenadas"
            )

    def do_POST(self):
        caminho = urlparse(self.path).path

        if caminho != "/salvar":
            self.send_error(404, "Endpoint não encontrado")
            return

        try:
            tamanho = int(
                self.headers.get("Content-Length", "0")
            )

            if tamanho <= 0 or tamanho > 10000:
                self.send_error(400, "Tamanho inválido")
                return

            corpo = self.rfile.read(tamanho)
            dados = json.loads(corpo)

            lat = float(dados["latitude"])
            lon = float(dados["longitude"])

            if not (
                math.isfinite(lat)
                and math.isfinite(lon)
                and -90 <= lat <= 90
                and -180 <= lon <= 180
            ):
                self.send_error(400, "Coordenadas inválidas")
                return

            # Salva permanentemente no PostgreSQL.
            with conectar() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO coordenadas (
                            latitude,
                            longitude
                        )
                        VALUES (%s, %s)
                    """, (lat, lon))

            print(f"Latitude: {lat}", flush=True)
            print(f"Longitude: {lon}", flush=True)
            print(
                f"Mapa: https://www.google.com/maps?q={lat},{lon}",
                flush=True
            )

            self.responder_json(200, {"ok": True})

        except (
            ValueError,
            KeyError,
            TypeError,
            json.JSONDecodeError
        ):
            self.send_error(400, "Dados inválidos")

        except Exception:
            print(
                "Erro ao salvar coordenadas no banco.",
                flush=True
            )
            self.send_error(
                500,
                "Erro ao salvar coordenadas"
            )


if __name__ == "__main__":
    inicializar_banco()

    porta = int(os.environ.get("PORT", "8000"))

    servidor = HTTPServer(
        ("0.0.0.0", porta),
        Handler
    )

    print(
        f"Servidor iniciado na porta {porta}",
        flush=True
    )

    servidor.serve_forever()
