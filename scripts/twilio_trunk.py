#!/usr/bin/env python3
"""Configura o Elastic SIP Trunk da Twilio para a ligação de saída da Agora ConvoAI.

Segue o guia "Set up SIP trunk" da Agora (Twilio). O script:
  1. cria (ou reaproveita) o trunk com a Termination URI <TWILIO_TRUNK_DOMINIO>.pstn.twilio.com;
  2. cria (ou reaproveita) uma IP Access Control List com os IPs SIP de saída da Agora e a vincula ao trunk;
  3. associa ao trunk o número da Twilio (TWILIO_NUMERO, que já precisa estar comprado na conta);
  4. imprime o que cadastrar na Agora (Console > Phone Numbers > Add Phone Number).

Não compra número, não imprime segredos. Credenciais vêm do ambiente (.env), nunca da linha de comando:
  TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_NUMERO (+1..., E.164), TWILIO_TRUNK_DOMINIO (ex.: avisai-chapahalls)

Uso (dentro do Docker):  make twilio
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.twilio.com/2010-04-01"
TRUNKING = "https://trunking.twilio.com/v1"
NOME = "avisai-agora"

# IPs SIP de saída da Agora (docs: /en/ai/studio/deploy/sip-trunk). A lista vale pelo DDI do número importado.
IPS_AGORA = {
    "+1": ["49.51.250.59", "49.51.250.76"],
    "latam_eu": [  # +55, +52, +54, +56, +51, +44, +33, +49, +39, +34, +61, +64
        "43.157.157.7", "43.157.180.46", "43.157.154.150", "43.157.147.39", "43.157.160.149", "43.157.170.160",
        "43.157.176.50", "43.157.182.24", "43.157.150.207", "43.157.146.198", "43.157.186.243", "43.157.149.172",
    ],
}


def env(nome: str) -> str:
    v = os.getenv(nome, "").strip()
    if not v:
        sys.exit(f"faltou {nome} no .env")
    return v


SID = env("TWILIO_ACCOUNT_SID")
_AUTH = "Basic " + base64.b64encode(f"{SID}:{env('TWILIO_AUTH_TOKEN')}".encode()).decode()


def req(metodo: str, url: str, dados: dict | None = None) -> dict:
    corpo = urllib.parse.urlencode(dados).encode() if dados else None
    r = urllib.request.Request(url, data=corpo, method=metodo, headers={
        "Authorization": _AUTH, "Content-Type": "application/x-www-form-urlencoded", "User-Agent": "avisai-setup"})
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            txt = resp.read()
            return json.loads(txt) if txt else {}
    except urllib.error.HTTPError as e:
        corpo_erro = e.read().decode(errors="ignore")[:400]
        sys.exit(f"Twilio {metodo} {url.split('?')[0]} -> HTTP {e.code}: {corpo_erro}")


def lista(url: str, chave: str) -> list[dict]:
    return req("GET", url + ("&" if "?" in url else "?") + "PageSize=200").get(chave, [])


def main() -> None:
    numero = env("TWILIO_NUMERO")
    dominio = env("TWILIO_TRUNK_DOMINIO").removesuffix(".pstn.twilio.com") + ".pstn.twilio.com"

    # 1. número precisa existir na conta
    nums = lista(f"{API}/Accounts/{SID}/IncomingPhoneNumbers.json?PhoneNumber={urllib.parse.quote(numero)}", "incoming_phone_numbers")
    if not nums:
        sys.exit(f"o número {numero} não está na conta Twilio (compre em Phone Numbers > Buy a number)")
    num_sid = nums[0]["sid"]

    # 2. trunk
    trunk = next((t for t in lista(f"{TRUNKING}/Trunks", "trunks") if t.get("friendly_name") == NOME), None)
    if not trunk:
        trunk = req("POST", f"{TRUNKING}/Trunks", {"FriendlyName": NOME, "DomainName": dominio})
        print(f"trunk criado: {trunk['sid']}")
    else:
        print(f"trunk existente: {trunk['sid']}")
    tk = trunk["sid"]
    dominio = trunk.get("domain_name") or dominio
    seguro = bool(trunk.get("secure"))

    # 3. IP ACL com os IPs da Agora (as duas listas, para +1 e +55)
    acls = lista(f"{API}/Accounts/{SID}/SIP/IpAccessControlLists.json", "ip_access_control_lists")
    acl = next((a for a in acls if a.get("friendly_name") == NOME), None) or req(
        "POST", f"{API}/Accounts/{SID}/SIP/IpAccessControlLists.json", {"FriendlyName": NOME})
    existentes = {i["ip_address"] for i in lista(f"{API}/Accounts/{SID}/SIP/IpAccessControlLists/{acl['sid']}/IpAddresses.json", "ip_addresses")}
    for ip in IPS_AGORA["+1"] + IPS_AGORA["latam_eu"]:
        if ip not in existentes:
            req("POST", f"{API}/Accounts/{SID}/SIP/IpAccessControlLists/{acl['sid']}/IpAddresses.json",
                {"FriendlyName": "agora-" + ip.replace(".", "-"), "IpAddress": ip})
    vinculadas = {a["sid"] for a in lista(f"{TRUNKING}/Trunks/{tk}/IpAccessControlLists", "ip_access_control_lists")}
    if acl["sid"] not in vinculadas:
        req("POST", f"{TRUNKING}/Trunks/{tk}/IpAccessControlLists", {"IpAccessControlListSid": acl["sid"]})
    print(f"ACL {acl['sid']} com {len(IPS_AGORA['+1']) + len(IPS_AGORA['latam_eu'])} IPs da Agora, vinculada ao trunk")

    # 4. número no trunk
    no_trunk = {p["sid"] for p in lista(f"{TRUNKING}/Trunks/{tk}/PhoneNumbers", "phone_numbers")}
    if num_sid not in no_trunk:
        req("POST", f"{TRUNKING}/Trunks/{tk}/PhoneNumbers", {"PhoneNumberSid": num_sid})
    print(f"número {numero} associado ao trunk")

    print("\n=== Cadastre na Agora: Console > Phone Numbers > Add Phone Number ===")
    print(f"  Phone Number:       {numero}")
    print("  Vendor:             SIP Trunk")
    print(f"  SIP Trunk Address:  {dominio}")
    print(f"  Transport Protocol: {'TLS' if seguro else 'TCP'}   (Secure Trunking {'ligado' if seguro else 'desligado'})")
    print("  Username/Password:  em branco (sem credential list)")
    print("\nDepois, no .env:  RECEBEDOR_MODO=sip  e  AGORA_SIP_FROM_NUMBER=" + numero)
    print("Lembrete: habilite o Brasil em Voice > Settings > Geo Permissions; conta trial só liga para números verificados.")


if __name__ == "__main__":
    main()
