
"""Aurum Core module."""

import os
from pprint import PrettyPrinter

import codecov
import pytest
from lxml import etree

from py_aurum import Aurum

pp = PrettyPrinter(indent=8)

# Prepare aiohttp app routes
# taking smile_setup (i.e. directory name under tests/{smile_app}/
# as inclusion point
def setup_app():
    global aurum_setup
    if not aurum_setup:
        return False
    app = aiohttp.web.Application()
    app.router.add_get("/core/appliances", smile_appliances)
    return app


# Wrapper for output uri
def aurum_data(request):
    global smile_setup
    f = open("tests/{}/core.appliances.xml".format(smile_setup), "r")
    data = f.read()
    f.close()
    return aiohttp.web.Response(text=data)


# Generic connect
@pytest.mark.asyncio
def collect_datat():
    global smile_setup
    if not smile_setup:
        return False
    port = aiohttp.test_utils.unused_port()

    app = await setup_app()

    server = aiohttp.test_utils.TestServer(
        app, port=port, scheme="http", host="127.0.0.1"
    )
    await server.start_server()

    client = aiohttp.test_utils.TestClient(server)
    websession = client.session

    url = "{}://{}:{}/core/modules".format(server.scheme, server.host, server.port)
    resp = await websession.get(url)
    assert resp.status == 200
    text = await resp.text()
    assert "xml" in text
    try:
        assert "<vendor_name>Plugwise</vendor_name>" in text
    except:
        # P1 v2 exception handling
        assert "<dsmrmain id" in text
        pass

    smile = Smile(
        host=server.host, password="abcdefgh", port=server.port, websession=websession,
    )
    assert smile._timeout == 20
    assert smile._domain_objects is None
    assert smile.smile_type is None

    """Connect to the smile"""
    connection = await smile.connect()
    assert connection is True
    assert smile.smile_type is not None
    return server, smile, client


# GEneric list_devices
@pytest.mark.asyncio
async def list_devices(server, smile):
    device_list = {}
    devices = await smile.get_all_devices()
    return devices
    ctrl_id = None
    plug_id = None
    ##for dev in devices:
    ##    if dev['name'] == 'Controlled Device':
    ##        ctrl_id = dev['id']
    ##    if dev['name'] == 'Home' and smile.smile_type == 'power':
    ##        ctrl_id = dev['id']
    for device, details in devices.items():
        # Detect home
        if "home" in details["type"]:
            ctrl_id = device
        elif "plug" in details["type"]:
            plug_id = device

        device_list[device] = {
            "name": details["name"],
            "type": details["type"],
            "ctrl": ctrl_id,
            "plug": plug_id,
            "location": details["location"],
        }

    return device_list


# Generic disconnect
@pytest.mark.asyncio
async def disconnect(server, client):
    if not server:
        return False
    await client.session.close()
    await server.close()


def show_setup(location_list, device_list):
    print("This smile looks like:")
    for loc_id, loc_info in location_list.items():
        pp = PrettyPrinter(indent=4)
        print("  --> Location: {} ({})".format(loc_info["name"], loc_id))
        for dev_id, dev_info in device_list.items():
            if dev_info["location"] == loc_id:
                print("      + Device: {} ({})".format(dev_info["name"], dev_id))


@pytest.mark.asyncio
async def test_device(smile=Smile, testdata={}):
    global smile_setup
    if testdata == {}:
        return False

    print("Asserting testdata:")
    device_list = smile.get_all_devices()
    location_list, home = smile.scan_thermostats()

    print("Gateway id = ", smile.gateway_id)
    show_setup(location_list, device_list)
    if True:
        print("Device list: {}".format(device_list))
        for dev_id, details in device_list.items():
            data = smile.get_device_data(dev_id)
            print("Device {} / {} data: {}".format(dev_id, details, data))

    for testdevice, measurements in testdata.items():
        assert testdevice in device_list
        # if testdevice not in device_list:
        #    print("Device {} to test against {} not found in device_list for {}".format(testdevice,measurements,smile_setup))
        # else:
        #    print("Device {} to test found in {}".format(testdevice,device_list))
        for dev_id, details in device_list.items():
            if testdevice == dev_id:
                data = smile.get_device_data(dev_id)
                print(
                    "- Testing data for device {} ({})".format(details["name"], dev_id)
                )
                for measure_key, measure_assert in measurements.items():
                    print(
                        "  + Testing {} (should be {})".format(
                            measure_key, measure_assert
                        )
                    )
                    assert data[measure_key] == measure_assert
    print("Single Master Thermostat?: {}".format(smile.single_master_thermostat()))


@pytest.mark.asyncio
async def tinker_relay(smile, dev_ids=[]):
    global smile_setup
    if not smile_setup:
        return False

    print("Asserting modifying settings for relay devices:")
    for dev_id in dev_ids:
        print("- Devices ({}):".format(dev_id))
        for new_state in [False, True, False]:
            print("- Switching {}".format(new_state))
            relay_change = await smile.set_relay_state(dev_id, new_state)
            assert relay_change == True


@pytest.mark.asyncio
async def tinker_thermostat(smile, loc_id, good_schemas=["Weekschema"]):
    global smile_setup
    if not smile_setup:
        return False

    print("Asserting modifying settings in location ({}):".format(loc_id))
    for new_temp in [20.0, 22.9]:
        print("- Adjusting temperature to {}".format(new_temp))
        temp_change = await smile.set_temperature(loc_id, new_temp)
        assert temp_change == True

    for new_preset in ["asleep", "home", "!bogus"]:
        assert_state = True
        warning = ""
        if new_preset[0] == "!":
            assert_state = False
            warning = " Negative test"
            new_preset = new_preset[1:]
        print("- Adjusting preset to {}{}".format(new_preset, warning))
        preset_change = await smile.set_preset(loc_id, new_preset)
        assert preset_change == assert_state

    if good_schemas is not []:
        good_schemas.append("!VeryBogusSchemaNameThatNobodyEverUsesOrShouldUse")
        for new_schema in good_schemas:
            assert_state = True
            warning = ""
            if new_schema[0] == "!":
                assert_state = False
                warning = " Negative test"
                new_schema = new_schema[1:]
            print("- Adjusting schedule to {}{}".format(new_schema, warning))
            schema_change = await smile.set_schedule_state(loc_id, new_schema, "auto")
            assert schema_change == assert_state
    else:
        print("- Skipping schema adjustments")


# Actual test for directory 'Anna' legacy
@pytest.mark.asyncio
async def test_connect_legacy_anna():
    # testdata is a dictionary with key ctrl_id_dev_id => keys:values
    # testdata={
    #             'ctrl_id': { 'outdoor+temp': 20.0, }
    #             'ctrl_id:dev_id': { 'type': 'thermostat', 'battery': None, }
    #         }
    testdata = {
        # Anna
        "04e4cbfe7f4340f090f85ec3b9e6a950": {
            "thermostat": 20.5,
            "temperature": 20.4,
            "illuminance": 0.8,
        },
        # Central
        "04e4cbfe7f4340f090f85ec3b9e6a950": {
            "domestic_hot_water_state": False,
            "boiler_temperature": 23.59,
            "central_heating_state": True,
            "central_heater_water_pressure": 1.2,
            "boiler_state": False,
        },
    }
    global smile_setup
    smile_setup = "legacy_anna"
    server, smile, client = await connect()
    assert smile.smile_type == "thermostat"
    assert smile.smile_version[0] == "1.8.0"
    assert smile._smile_legacy == True
    await test_device(smile, testdata)
    await tinker_thermostat(
        smile,
        "c34c6864216446528e95d88985e714cc",
        good_schemas=["Thermostat schedule",],
    )
    await smile.close_connection()
    await disconnect(server, client)


# Actual test for directory 'P1' v2
@pytest.mark.asyncio
async def test_connect_smile_p1_v2():
    # testdata dictionary with key ctrl_id_dev_id => keys:values
    testdata = {
        # Gateway / P1 itself
        "938696c4bcdb4b8a9a595cb38ed43913": {
            "electricity_consumed_peak_point": 458.0,
            "net_electricity_point": 458.0,
            "gas_consumed_cumulative": 584.433,
            "electricity_produced_peak_cumulative": 1296136.0,
            "electricity_produced_off_peak_cumulative": 482598.0,
        }
    }
    global smile_setup
    smile_setup = "smile_p1_v2"
    server, smile, client = await connect()
    assert smile.smile_type == "power"
    assert smile.smile_version[0] == "2.5.9"
    assert smile._smile_legacy == True
    await test_device(smile, testdata)
    await smile.close_connection()
    await disconnect(server, client)

    await smile.close_connection()
    await disconnect(server, client)


# Actual test for directory 'P1' v2 2nd version
@pytest.mark.asyncio
async def test_connect_smile_p1_v2_2():
    # testdata dictionary with key ctrl_id_dev_id => keys:values
    testdata = {
        # Gateway / P1 itself
        "199aa40f126840f392983d171374ab0b": {
            "electricity_consumed_peak_point": 368.0,
            "net_electricity_point": 368.0,
            "gas_consumed_cumulative": 2637.993,
            "electricity_produced_peak_cumulative": 0.0,
        }
    }
    global smile_setup
    smile_setup = "smile_p1_v2_2"
    server, smile, client = await connect()
    assert smile.smile_type == "power"
    assert smile.smile_version[0] == "2.5.9"
    assert smile._smile_legacy == True
    await test_device(smile, testdata)
    await smile.close_connection()
    await disconnect(server, client)

    await smile.close_connection()
    await disconnect(server, client)


# Actual test for directory 'Anna' without a boiler
@pytest.mark.asyncio
async def test_connect_anna_v4():
    # testdata is a dictionary with key ctrl_id_dev_id => keys:values
    # testdata={
    #             'ctrl_id': { 'outdoor+temp': 20.0, }
    #             'ctrl_id:dev_id': { 'type': 'thermostat', 'battery': None, }
    #         }
    testdata = {
        # Anna
        "01b85360fdd243d0aaad4d6ac2a5ba7e": {
            "selected_schedule": None,
            "illuminance": 60.0,
            "active_preset": "home",
        },
        # Central
        "cd0e6156b1f04d5f952349ffbe397481": {
            "central_heating_state": True,
            "central_heater_water_pressure": 2.1,
            "boiler_temperature": 52.0,
        },
        "0466eae8520144c78afb29628384edeb": {"outdoor_temperature": 7.4,},
    }
    global smile_setup
    smile_setup = "anna_v4"
    server, smile, client = await connect()
    assert smile.smile_type == "thermostat"
    assert smile.smile_version[0] == "4.0.15"
    assert smile._smile_legacy == False
    await test_device(smile, testdata)
    await tinker_thermostat(
        smile,
        "eb5309212bf5407bb143e5bfa3b18aee",
        good_schemas=["Standaard", "Thuiswerken"],
    )
    await smile.close_connection()
    await disconnect(server, client)


# Actual test for directory 'Anna' without a boiler
@pytest.mark.asyncio
async def test_connect_anna_without_boiler():
    # testdata is a dictionary with key ctrl_id_dev_id => keys:values
    # testdata={
    #             'ctrl_id': { 'outdoor+temp': 20.0, }
    #             'ctrl_id:dev_id': { 'type': 'thermostat', 'battery': None, }
    #         }
    testdata = {
        # Anna
        "7ffbb3ab4b6c4ab2915d7510f7bf8fe9": {
            "selected_schedule": "Normal",
            "illuminance": 35.0,
            "active_preset": "away",
        },
        "a270735e4ccd45239424badc0578a2b1": {"outdoor_temperature": 10.8,},
        # Central
        "c46b4794d28149699eacf053deedd003": {"central_heating_state": False,},
    }
    global smile_setup
    smile_setup = "anna_without_boiler"
    server, smile, client = await connect()
    assert smile.smile_type == "thermostat"
    assert smile.smile_version[0] == "3.1.11"
    assert smile._smile_legacy == False
    await test_device(smile, testdata)
    await tinker_thermostat(
        smile, "c34c6864216446528e95d88985e714cc", good_schemas=["Test", "Normal"]
    )
    await smile.close_connection()
    await disconnect(server, client)


"""

# Actual test for directory 'Adam'
# living room floor radiator valve and separate zone thermostat
# an three rooms with conventional radiators
@pytest.mark.asyncio
async def test_connect_adam():
    global smile_setup
    smile_setup = 'adam_living_floor_plus_3_rooms'
    server,smile,client = await connect()
    device_list = await list_devices(server,smile)
    #assert smile.smile_type == 'thermostat'
    print(device_list)
    #testdata dictionary with key ctrl_id_dev_id => keys:values
    testdata={}
    for dev_id,details in device_list.items():
        data = smile.get_device_data(dev_id, details['ctrl'], details['plug'])
        test_id = '{}_{}'.format(details['ctrl'],dev_id)
        #if test_id not in testdata:
        #    continue
        print(data)

    await smile.close_connection()
    await disconnect(server,client)

"""

# Actual test for directory 'Adam + Anna'
@pytest.mark.asyncio
async def test_connect_adam_plus_anna():
    # testdata dictionary with key ctrl_id_dev_id => keys:values
    testdata = {
        # Anna
        "ee62cad889f94e8ca3d09021f03a660b": {
            "selected_schedule": "Weekschema",
            "last_used": "Weekschema",
            "illuminance": None,
            "active_preset": "home",
            "thermostat": 20.5,  # HA setpoint_temp
            "temperature": 20.46,  # HA current_temp
        },
        # Central
        "2743216f626f43948deec1f7ab3b3d70": {
            "central_heating_state": False,
            "central_heater_water_pressure": 6.0,
        },
        "b128b4bbbd1f47e9bf4d756e8fb5ee94": {"outdoor_temperature": 11.9,},
        # Plug MediaCenter
        "aa6b0002df0a46e1b1eb94beb61eddfe": {
            "electricity_consumed": 10.31,
            "relay": True,
        },
    }
    global smile_setup
    smile_setup = "adam_plus_anna"
    server, smile, client = await connect()
    assert smile.smile_type == "thermostat"
    assert smile.smile_version[0] == "3.0.15"
    assert smile._smile_legacy == False
    await test_device(smile, testdata)
    await tinker_thermostat(
        smile, "009490cc2f674ce6b576863fbb64f867", good_schemas=["Weekschema"]
    )
    await tinker_relay(smile, ["aa6b0002df0a46e1b1eb94beb61eddfe"])
    await smile.close_connection()
    await disconnect(server, client)


# Actual test for directory 'Adam + Anna'
@pytest.mark.asyncio
async def test_connect_adam_zone_per_device():
    # testdata dictionary with key ctrl_id_dev_id => keys:values
    testdata = {
        # Lisa WK
        "b59bcebaf94b499ea7d46e4a66fb62d8": {
            "thermostat": 21.5,
            "temperature": 21.1,
            "battery": 0.34,
        },
        # Floor WK
        "b310b72a0e354bfab43089919b9a88bf": {
            "thermostat": 21.5,
            "temperature": 26.22,
            "valve_position": 1.0,
        },
        # CV pomp
        "78d1126fc4c743db81b61c20e88342a7": {
            "electricity_consumed": 35.81,
            "relay": True,
        },
        # Lisa Bios
        "df4a4a8169904cdb9c03d61a21f42140": {
            "thermostat": 13.0,
            "temperature": 16.5,
            "battery": 0.67,
        },
        # Adam
        "90986d591dcd426cae3ec3e8111ff730": {"central_heating_state": True,},
        "fe799307f1624099878210aa0b9f1475": {"outdoor_temperature": 7.7,},
        # Modem
        "675416a629f343c495449970e2ca37b5": {
            "electricity_consumed": 12.19,
            "relay": True,
        },
    }
    global smile_setup
    smile_setup = "adam_zone_per_device"
    server, smile, client = await connect()
    assert smile.smile_type == "thermostat"
    assert smile.smile_version[0] == "3.0.15"
    assert smile._smile_legacy == False
    await test_device(smile, testdata)
    await tinker_thermostat(
        smile, "c50f167537524366a5af7aa3942feb1e", good_schemas=["GF7  Woonkamer"]
    )
    await tinker_thermostat(
        smile, "82fa13f017d240daa0d0ea1775420f24", good_schemas=["CV Jessie"]
    )
    await tinker_relay(smile, ["675416a629f343c495449970e2ca37b5"])
    await smile.close_connection()
    await disconnect(server, client)


# Actual test for directory 'Adam + Anna'
@pytest.mark.asyncio

# {'electricity_consumed_peak_point': 644.0, 'electricity_consumed_off_peak_point': 0.0, 'electricity_consumed_peak_cumulative': 7702167.0, 'electricity_consumed_off_peak_cumulative': 10263159.0, 'electricity_produced_off_peak_point': 0.0, 'electricity_produced_peak_cumulative': 0.0, 'electricity_produced_off_peak_cumulative': 0.0}
# Actual test for directory 'Adam + Anna'
@pytest.mark.asyncio
async def test_connect_adam_multiple_devices_per_zone():
    global smile_setup
    smile_setup = "adam_multiple_devices_per_zone"
    server, smile, client = await connect()
    device_list = smile.get_all_devices()
    location_list, home = smile.match_locations()
    for loc_id, loc_info in location_list.items():
        print("  --> Location: {} ({}) - {}".format(loc_info["name"], loc_id, loc_info))
        for dev_id, dev_info in device_list.items():
            if dev_info["location"] == loc_id:
                print(
                    "      + Device: {} ({}) - {}".format(
                        dev_info["name"], dev_id, dev_info
                    )
                )
    for dev_id, details in device_list.items():
        data = smile.get_device_data(dev_id)
        print("Device {} / {} data: {}".format(dev_id, details, data))


# {'electricity_consumed_peak_point': 644.0, 'electricity_consumed_off_peak_point': 0.0, 'electricity_consumed_peak_cumulative': 7702167.0, 'electricity_consumed_off_peak_cumulative': 10263159.0, 'electricity_produced_off_peak_point': 0.0, 'electricity_produced_peak_cumulative': 0.0, 'electricity_produced_off_peak_cumulative': 0.0}
# Actual test for directory 'P1 v3'
@pytest.mark.asyncio
async def test_connect_p1v3():
    # testdata dictionary with key ctrl_id_dev_id => keys:values
    testdata = {
        # Gateway / P1 itself
        "ba4de7613517478da82dd9b6abea36af": {
            "electricity_consumed_peak_point": 644.0,
            "electricity_produced_peak_cumulative": 0.0,
            "electricity_consumed_off_peak_cumulative": 10263159.0,
        }
    }
    global smile_setup
    smile_setup = "p1v3"
    server, smile, client = await connect()
    assert smile.smile_type == "power"
    assert smile.smile_version[0] == "3.3.6"
    assert smile._smile_legacy == False
    await test_device(smile, testdata)
    await smile.close_connection()
    await disconnect(server, client)


# Faked solar for differential, need actual p1v3 with solar data :)
@pytest.mark.asyncio
async def test_connect_p1v3solarfake():
    # testdata dictionary with key ctrl_id_dev_id => keys:values
    testdata = {
        # Gateway / P1 itself
        "ba4de7613517478da82dd9b6abea36af": {
            "electricity_consumed_peak_point": 644.0,
            "electricity_produced_peak_cumulative": 20000.0,
            "electricity_consumed_off_peak_cumulative": 10263159.0,
            "net_electricity_point": 244.0,
        }
    }
    global smile_setup
    smile_setup = "p1v3solarfake"
    server, smile, client = await connect()
    assert smile.smile_type == "power"
    assert smile.smile_version[0] == "3.3.6"
    assert smile._smile_legacy == False
    await test_device(smile, testdata)
    await smile.close_connection()
    await disconnect(server, client)


# Full option p1v3
@pytest.mark.asyncio
async def test_connect_p1v3_full_option():
    # testdata dictionary with key ctrl_id_dev_id => keys:values
    testdata = {
        # Gateway / P1 itself
        "e950c7d5e1ee407a858e2a8b5016c8b3": {
            "electricity_consumed_peak_point": 0.0,
            "electricity_produced_peak_cumulative": 396559.0,
            "electricity_consumed_off_peak_cumulative": 551090.0,
            "electricity_produced_peak_point": 2809.0,
            "net_electricity_point": -2809.0,
            "gas_consumed_cumulative": 584.85,
        }
    }
    global smile_setup
    smile_setup = "p1v3_full_option"
    server, smile, client = await connect()
    assert smile.smile_type == "power"
    assert smile.smile_version[0] == "3.3.9"
    assert smile._smile_legacy == False
    await test_device(smile, testdata)
    await smile.close_connection()
    await disconnect(server, client)


# Heatpump Anna
@pytest.mark.asyncio
async def test_connect_anna_heatpump():
    # testdata dictionary with key ctrl_id_dev_id => keys:values
    testdata = {
        # Anna
        "3cb70739631c4d17a86b8b12e8a5161b": {
            "selected_schedule": "standaard",
            "illuminance": 86.0,
            "active_preset": "home",
        },
        # Central
        "1cbf783bb11e4a7c8a6843dee3a86927": {
            "domestic_hot_water_state": False,
            "boiler_temperature": 29.09,
            "central_heater_water_pressure": 1.57,
        },
        "015ae9ea3f964e668e490fa39da3870b": {"outdoor_temperature": 18.0,},
    }
    global smile_setup
    smile_setup = "anna_heatpump"
    server, smile, client = await connect()
    assert smile.smile_type == "thermostat"
    assert smile.smile_version[0] == "4.0.15"
    assert smile._smile_legacy == False
    await test_device(smile, testdata)
    await smile.close_connection()
    await disconnect(server, client)


# Heatpump Anna in cooling mode
@pytest.mark.asyncio
async def test_connect_anna_heatpump_cooling():
    # testdata dictionary with key ctrl_id_dev_id => keys:values
    testdata = {
        # Anna
        "3cb70739631c4d17a86b8b12e8a5161b": {
            "selected_schedule": None,
            "illuminance": 25.5,
            "active_preset": "home",
        },
        # Central
        "1cbf783bb11e4a7c8a6843dee3a86927": {
            "domestic_hot_water_state": False,
            "boiler_temperature": 24.69,
            "central_heater_water_pressure": 1.61,
        },
        "015ae9ea3f964e668e490fa39da3870b": {"outdoor_temperature": 21.0,},
    }
    global smile_setup
    smile_setup = "anna_heatpump_cooling"
    server, smile, client = await connect()
    assert smile.smile_type == "thermostat"
    assert smile.smile_version[0] == "4.0.15"
    assert smile._smile_legacy == False
    await test_device(smile, testdata)
    await smile.close_connection()
    await disconnect(server, client)
