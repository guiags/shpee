
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import json
import os

PASTA = Path(__file__).resolve().parent


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PASTA), **kwargs)

    def do_POST(self):
        if self.path != "/salvar":
            self.send_error(404)
            return

        try:
            tamanho = int(self.headers.get("Content-Length", "0"))
            if tamanho <= 0 or tamanho > 10000:
                self.send_error(400, "Tamanho inválido")
                return

            dados = json.loads(self.rfile.read(tamanho))
            lat = float(dados["latitude"])
            lon = float(dados["longitude"])

            print(f"Latitude: {lat}", flush=True)
            print(f"Longitude: {lon}", flush=True)
            print(
                f"Mapa: https://www.google.com/maps?q={lat},{lon}",
                flush=True
            )
            
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                self.send_error(400, "Coordenadas inválidas")
                return

            conteudo = (
                f"Latitude: {lat}\n"
                f"Longitude: {lon}\n"
                f"Mapa: https://www.google.com/maps?q={lat},{lon}\n"
            )

            (PASTA / "coordenadas.txt").write_text(
                conteudo, encoding="utf-8"
            )

            resposta = json.dumps({"ok": True}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resposta)))
            self.end_headers()
            self.wfile.write(resposta)

        except (ValueError, KeyError, json.JSONDecodeError):
            self.send_error(400, "Dados inválidos")


if __name__ == "__main__":
    porta = int(os.environ.get("PORT", "8000"))
    servidor = HTTPServer(("0.0.0.0", porta), Handler)
    print(f"Servidor iniciado na porta {porta}")
    servidor.serve_forever()
