"""Cliente único para a Evolution API.

Centraliza normalização de número, conexão, diagnóstico e envio de texto. Isso
remove diferenças de payload/timeout entre disparo em lote, teste e chat manual.
"""
import logging
import re

import requests

from config import CONFIG

logger = logging.getLogger(__name__)


class EvolutionError(RuntimeError):
    def __init__(self, message, status_code=None, endpoint=None, body=None):
        super().__init__(message)
        self.status_code = status_code
        self.endpoint = endpoint
        self.body = body


class EvolutionClient:
    def __init__(self, base_url=None, instance=None, api_key=None, timeout=30):
        self.base_url = (base_url if base_url is not None else CONFIG.get("webhook_whatsapp", "")).strip().rstrip("/")
        self.instance = (instance if instance is not None else CONFIG.get("evolution_instance", "")).strip()
        self.api_key = (api_key if api_key is not None else CONFIG.get("evolution_api_key", "")).strip()
        self.timeout = timeout

    @property
    def configured(self):
        return bool(self.base_url and self.instance and self.api_key)

    @property
    def headers(self):
        return {"apikey": self.api_key, "Content-Type": "application/json"}

    @staticmethod
    def normalizar_numero(numero):
        digitos = re.sub(r"\D", "", str(numero or ""))
        if digitos and not digitos.startswith("55"):
            digitos = "55" + digitos
        return digitos

    def _request(self, method, path, **kwargs):
        if not self.configured:
            raise EvolutionError("Evolution API não configurada.")
        url = f"{self.base_url}{path}"
        kwargs.setdefault("headers", self.headers)
        kwargs.setdefault("timeout", self.timeout)
        try:
            resp = requests.request(method, url, **kwargs)
        except requests.RequestException as exc:
            raise EvolutionError(
                f"Falha de conexão com Evolution API: {exc}",
                endpoint=path,
            ) from exc

        try:
            body = resp.json()
        except Exception:
            body = (resp.text or "")[:1000]

        if not resp.ok:
            resumo = body if isinstance(body, str) else str(body)
            raise EvolutionError(
                f"Evolution HTTP {resp.status_code}: {resumo[:400]}",
                status_code=resp.status_code,
                endpoint=path,
                body=body,
            )
        return body

    def connection_state(self):
        """Retorna estado real do monitor da instância (`open`, `close`, etc.)."""
        if not self.configured:
            return {"configurado": False, "conectado": False, "state": ""}
        try:
            data = self._request("GET", f"/instance/connectionState/{self.instance}", timeout=10)
            if not isinstance(data, dict):
                data = {}
            state = (
                (data.get("instance") or {}).get("state")
                or data.get("state")
                or ""
            )
            state = str(state).lower()
            return {
                "configurado": True,
                "conectado": state in ("open", "connected"),
                "state": state,
                "raw": data,
            }
        except EvolutionError as exc:
            return {
                "configurado": True,
                "conectado": False,
                "state": "",
                "erro": str(exc),
                "http_status": exc.status_code,
            }

    def fetch_instance(self):
        """Busca metadados da instância para diagnóstico, sem alterar sessão."""
        if not self.configured:
            return None
        try:
            data = self._request(
                "GET", "/instance/fetchInstances",
                params={"instanceName": self.instance},
                timeout=12,
            )
        except EvolutionError:
            return None

        itens = data if isinstance(data, list) else (data.get("instances", []) if isinstance(data, dict) else [])
        if isinstance(itens, dict):
            itens = [itens]
        for item in itens or []:
            nome = item.get("name") or item.get("instanceName") or (item.get("instance") or {}).get("instanceName")
            if nome == self.instance:
                return item
        return itens[0] if itens else None

    def diagnostico(self):
        state = self.connection_state()
        info = self.fetch_instance() if state.get("configurado") else None
        numero = ""
        profile = ""
        if isinstance(info, dict):
            numero = str(info.get("number") or (info.get("instance") or {}).get("number") or "")
            profile = str(info.get("profileName") or (info.get("instance") or {}).get("profileName") or "")
        return {
            **state,
            "instance": self.instance or None,
            "numero": numero,
            "profile_name": profile,
            "config": {
                "webhook_url": self.base_url or None,
                "instance": self.instance or None,
                "api_key_mask": (
                    self.api_key[:4] + "****" + self.api_key[-2:]
                    if len(self.api_key) > 6 else ("****" if self.api_key else None)
                ),
            },
            "instance_info": info,
        }

    def send_text(self, numero, texto, delay_ms=None, quoted=None):
        numero = self.normalizar_numero(numero)
        if not numero:
            raise EvolutionError("Número vazio/inválido para envio.")
        texto = str(texto or "").strip()
        if not texto:
            raise EvolutionError("Mensagem vazia.")

        payload = {"number": numero, "text": texto}
        if delay_ms and delay_ms > 0:
            payload["delay"] = int(delay_ms)
            payload["presence"] = "composing"
        if quoted and (quoted.get("key") or {}).get("id"):
            payload["quoted"] = {"key": quoted["key"]}
            if quoted.get("message"):
                payload["quoted"]["message"] = quoted["message"]

        return self._request(
            "POST",
            f"/message/sendText/{self.instance}",
            json=payload,
            timeout=max(self.timeout, 60),
        )
