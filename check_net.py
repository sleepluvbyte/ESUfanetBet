"""Проверка сетевого доступа к api.telegram.org.

Запуск:  python check_net.py
"""

import socket

import config

HOST = "api.telegram.org"
PORT = 443


def _try(host, port, family, label):
    try:
        infos = socket.getaddrinfo(host, port, family, socket.SOCK_STREAM)
    except OSError as exc:
        print(f"  {label}: DNS ошибка — {exc}")
        return False
    if not infos:
        print(f"  {label}: нет адресов")
        return False
    for family_, _, _, _, sockaddr in infos[:2]:
        ip = sockaddr[0]
        sock = socket.socket(family_, socket.SOCK_STREAM)
        sock.settimeout(5)
        try:
            sock.connect(sockaddr)
            print(f"  {label}: {ip}:{port} — OK ✅")
            return True
        except OSError as exc:
            print(f"  {label}: {ip}:{port} — НЕДОСТУПНО ❌ ({exc})")
        finally:
            sock.close()
    return False


def main():
    print(f"Проверка доступа к Telegram ({HOST}:{PORT})\n")

    print("DNS:")
    try:
        addrs = socket.getaddrinfo(HOST, PORT, proto=socket.IPPROTO_TCP)
        for family_, _, _, _, sockaddr in addrs:
            print(f"  {sockaddr[0]}")
    except OSError as exc:
        print(f"  ошибка DNS: {exc}")

    print("\nTCP-подключение:")
    ipv4 = _try(HOST, PORT, socket.AF_INET, "IPv4")
    ipv6 = _try(HOST, PORT, socket.AF_INET6, "IPv6")

    print("\nДля сравнения, Google Sheets:")
    _try("sheets.googleapis.com", 443, socket.AF_INET, "IPv4")

    print()
    if config.PROXY_URL:
        print(f"PROXY_URL задан в .env: {config.PROXY_URL}")
        print("Если напрямую Telegram недоступен — запускай бота с этим прокси.")
    else:
        print("PROXY_URL не задан (.env).")

    if ipv4 or ipv6:
        print("\nИТОГ: Telegram доступен напрямую. Можно запускать run.py.")
    else:
        print(
            "\nИТОГ: Telegram НЕДОСТУПЕН. Нужен прокси или VPN.\n"
            "Пропиши в .env, например:\n"
            "  PROXY_URL=socks5://user:pass@host:1080\n"
            "и выполни: pip install aiohttp-socks"
        )


if __name__ == "__main__":
    main()
