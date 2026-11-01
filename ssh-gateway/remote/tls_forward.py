"""Serve TLS on 127.0.0.1:<listen_port> and forward the decrypted bytes to a
local gateway on 127.0.0.1:<target_port>.

This is a plain TCP pipe after the TLS handshake, so streaming responses work
unchanged. It does not rewrite HTTP headers; use Caddy (see mac/Caddyfile)
when the gateway checks the Host header.

Usage: python3 tls_forward.py LISTEN_PORT TARGET_PORT CERT KEY
"""
import asyncio
import ssl
import sys


async def pipe(reader, writer):
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, ssl.SSLError, asyncio.CancelledError):
        pass
    finally:
        writer.close()


def make_handler(target_port):
    async def handle(client_r, client_w):
        try:
            up_r, up_w = await asyncio.open_connection("127.0.0.1", target_port)
        except OSError:
            client_w.close()
            return
        await asyncio.gather(pipe(client_r, up_w), pipe(up_r, client_w))

    return handle


async def main():
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    listen_port, target_port, cert, key = sys.argv[1:5]
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(cert, key)
    server = await asyncio.start_server(
        make_handler(int(target_port)), "127.0.0.1", int(listen_port), ssl=ctx
    )
    async with server:
        await server.serve_forever()


asyncio.run(main())
