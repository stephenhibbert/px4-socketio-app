#!/usr/bin/env python3

import asyncio

from mavsdk import System
from mavsdk.mission import (MissionItem, MissionPlan)
import asyncio

import http.client
import json
import random
from urllib.parse import quote_plus

from haversine import Haversine
import numpy as np
import os
import time

import socketio

lat0, lon0 = 51.477985, 0.0 # Prime Meridian
lat0, lon0 =  51.517290431455976, -0.10424092952553489 # AWS Office
lat0, lon0 =  51.50813980651898, -0.09708083901920365 # Shakespeare's Globe

# connect to the redis queue as an external process
external_sio = socketio.RedisManager('redis://127.0.0.1:6379')

class Mission:
    """
    A class used to represent a drone mission in MAVSDK-Python

    ...

    Attributes
    ----------
    drone_id : int
        the index of the drone (0-255)
    lat : str
        the starting latitude of the drone
    lon : str
        the starting logitude of the drone

    Methods
    -------
    run()
        Launches the mission for the drone at the start lat, lon provided in the constructor
    """
    
    def __init__(self, drone_id, lat, lon):
        self.drone_id = int(drone_id)
        self.lat = lat
        self.lon = lat

    async def print_flight_mode(self, drone):
        """ Prints the flight mode when it changes """
    
        previous_flight_mode = None
    
        async for flight_mode in drone.telemetry.flight_mode():
            if flight_mode != previous_flight_mode:
                previous_flight_mode = flight_mode
                print(f"Flight mode: {flight_mode}")
                
    async def print_mission_progress(self, drone):
        async for mission_progress in drone.mission.mission_progress():
            print(f"Mission progress: "
                  f"{mission_progress.current}/"
                  f"{mission_progress.total}")
    
    # Position co-routine
    async def print_position(self, drone):
        async for position in drone.telemetry.position():
            # print(position.latitude_deg, position.longitude_deg)
            await asyncio.sleep(1) # hack to get 1Hz data
            
            data_label = { 
                "drone": self.drone_id,
                "lat": position.latitude_deg, 
                "lon": position.longitude_deg
            }
            
            external_sio.emit('my_response', {
                    'data': json.dumps(data_label)
            })

    async def observe_is_in_air(self, drone, running_tasks):
        """ Monitors whether the drone is flying or not and
        returns after landing """
    
        was_in_air = False
    
        async for is_in_air in drone.telemetry.in_air():
            if is_in_air:
                was_in_air = is_in_air
    
            if was_in_air and not is_in_air:
                for task in running_tasks:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                await asyncio.get_event_loop().shutdown_asyncgens()
    
                return
            
    async def run(self):
        
        local_port = 50040 + self.drone_id
        external_port = 14540 + self.drone_id
        
        external_sio.emit('my_response', {
            'data': json.dumps(str(self.drone_id) + ":" + str(local_port) + ":" + str(external_port))
        })

        drone = System(mavsdk_server_address="127.0.0.1", port=local_port)
        await drone.connect(system_address=f"udp://:{external_port}")
        
        conn = http.client.HTTPSConnection("api.postcodes.io")
        conn.request("GET", "/random/postcodes?outcode=SE1")
        r1 = conn.getresponse()
        print(r1.status, r1.reason)
        data1 = r1.read()
        json1 = json.loads(data1)
        postcode1 = json1['result']['postcode']
        lat1 = json1['result']['latitude']
        lon1 = json1['result']['longitude']
        print(postcode1, lat1, lon1)
        print("Haversine distance: ", Haversine([lat0,lon0],[lat1,lon1]).meters, "meters")
    
        print("Waiting for drone to connect...")
        async for state in drone.core.connection_state():
            if state.is_connected:
                print(f"-- Connected to drone {self.drone_id}")
                break
        
        print_flight_mode_task = asyncio.ensure_future(
            self.print_flight_mode(drone)
        )
    
        print_mission_progress_task = asyncio.ensure_future(
            self.print_mission_progress(drone)
        )
        
        print_position_task = asyncio.ensure_future(
            self.print_position(drone)
        )
    
        running_tasks = [print_mission_progress_task, print_flight_mode_task, print_position_task]
        termination_task = asyncio.ensure_future(
            self.observe_is_in_air(drone, running_tasks)
        )
    
        mission_items = []
        
        # latitude is the x-coordinate
        # longitude is the y-coordinate
        # lets say we wanted to figure out a series of points between the two given with linear interpolation
        
        latitudes = np.linspace(lat0, lat1, 10)  # ten points
        longitudes = (lon1 - lon0)/(lat1 - lat0)*(latitudes - lat0) + lon0
        
        for x, y in zip(latitudes, longitudes):
            mission_items.append(MissionItem(x,
                                             y,
                                             25,
                                             10,
                                             True,
                                             float('nan'),
                                             float('nan'),
                                             MissionItem.CameraAction.NONE,
                                             float('nan'),
                                             float('nan'),
                                             float('nan'),
                                             float('nan'),
                                             float('nan')))
    
        mission_plan = MissionPlan(mission_items)
    
        await drone.mission.set_return_to_launch_after_mission(True)
    
        print("-- Uploading mission")
        await drone.mission.upload_mission(mission_plan)
    
        print("Waiting for drone to have a global position estimate...")
        async for health in drone.telemetry.health():
            if health.is_global_position_ok and health.is_home_position_ok:
                print("-- Global position estimate OK")
                break
    
        print("-- Arming")
        await drone.action.arm()
    
        print("-- Starting mission")
        await drone.mission.start_mission()
    
        await termination_task
    