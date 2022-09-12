from aiohttp import web
from mission import Mission

import socketio
import redis
import os

import subprocess
import time

import asyncio

binary_path = '/usr/local/lib/python3.8/site-packages/mavsdk/bin/mavsdk_server'

mgr = socketio.AsyncRedisManager('redis://127.0.0.1:6379')
sio = socketio.AsyncServer(async_mode='aiohttp', client_manager=mgr)
app = web.Application()
sio.attach(app)

procs = []

async def stop_mavsdk(n_drones):
    for proc in procs:
        proc.kill()

async def start_mavsdk(n_drones):
    drone_ids = list(range(n_drones))
    for x in drone_ids:
        internal_port = 50040 + x
        external_port = 14540 + x
        
        args = f'-p {internal_port} udp://:{external_port}'
        print(args)
        call_str = '{} {}'.format(binary_path, args)
        p = subprocess.Popen(call_str, shell=True)
        procs.append(p)

async def index(request):
    with open('app.html') as f:
        return web.Response(text=f.read(), content_type='text/html')

@sio.event
async def launch(sid, message):
    print(message)
    n_drones = int(message['data'])
    await sio.emit('my_response', {'data': f"Stopping MAVSDK..."})
    await stop_mavsdk(n_drones)
    await sio.emit('my_response', {'data': f"Starting MAVSDK..."})
    await start_mavsdk(n_drones)
    await sio.emit('my_response', {'data': f"Launching {n_drones} drones...."})
    missions = []
    drone_ids = list(range(n_drones))
    for x in drone_ids:
        await sio.emit('my_response', {'data': f"Launching {x}"})
        missions.append(Mission(x, 51.517290431455976, -0.10424092952553489).run())
    
    tasks = asyncio.gather(*missions)
    await tasks
    

@sio.event
async def my_event(sid, message):
    await sio.emit('my_response', {'data': message['data']}, room=sid)


@sio.event
async def my_broadcast_event(sid, message):
    await sio.emit('my_response', {'data': message['data']})


@sio.event
async def join(sid, message):
    sio.enter_room(sid, message['room'])
    await sio.emit('my_response', {'data': 'Entered room: ' + message['room']},
                   room=sid)


@sio.event
async def leave(sid, message):
    sio.leave_room(sid, message['room'])
    await sio.emit('my_response', {'data': 'Left room: ' + message['room']},
                   room=sid)


@sio.event
async def close_room(sid, message):
    await sio.emit('my_response',
                   {'data': 'Room ' + message['room'] + ' is closing.'},
                   room=message['room'])
    await sio.close_room(message['room'])


@sio.event
async def my_room_event(sid, message):
    await sio.emit('my_response', {'data': message['data']},
                   room=message['room'])


@sio.event
async def disconnect_request(sid):
    await sio.disconnect(sid)


@sio.event
async def connect(sid, environ):
    await sio.emit('my_response', {'data': 'Connected', 'count': 0}, room=sid)


@sio.event
def disconnect(sid):
    print('Client disconnected')

app.router.add_static('/static', 'static')
app.router.add_get('/', index)

async def init_app():
    return app


if __name__ == '__main__':
    web.run_app(init_app(), port=8082)
