#encoding: utf-8
import math
from sgp4.api import Satrec, WGS84
from skyfield.api import load, wgs84, EarthSatellite
from datetime import datetime
import numpy as np
import os

from starrynet.sn_utils import *

_ = inf = 999999  # inf

# To calculate the connection between satellites and GSes in time_in
# fac_num: number of GSes


class Observer():

    def __init__(self, file_path, configuration_file_path, inclination,
                 satellite_altitude, orbit_number, sat_number, duration,
                 antenna_number, GS_lat_long, antenna_inclination,
                 intra_routing, hello_interval, AS):
        self.file_path = file_path
        self.configuration_file_path = configuration_file_path
        self.inclination = inclination
        self.satellite_altitude = satellite_altitude
        self.orbit_number = orbit_number
        self.sat_number = sat_number
        self.duration = duration
        self.antenna_number = antenna_number
        self.GS_lat_long = GS_lat_long
        self.antenna_inclination = antenna_inclination
        self.intra_routing = intra_routing
        self.hello_interval = hello_interval
        self.AS = AS

    def access_P_L_shortest(self, sat_cbf, fac_cbf, fac_num, sat_num,
                            num_orbits, num_sats_per_orbit, duration, fac_ll,
                            sat_lla, bound_dis, alpha, antenna_num, path):
        delay_matrix = np.zeros((fac_num + sat_num, fac_num + sat_num))
        for cur_time in range(duration):
            for i in range(0, fac_num):
                access_list = {}
                fac_lat = float(fac_ll[i][0])  # latitude
                up_lat = fac_lat + alpha  # bound
                down_lat = fac_lat - alpha
                x2 = fac_cbf[i][0]
                y2 = fac_cbf[i][1]
                z2 = fac_cbf[i][2]
                for j in range(0, sat_num):
                    if sat_lla[cur_time][j][0] >= down_lat and sat_lla[
                            cur_time][j][0] <= up_lat:
                        x1 = sat_cbf[cur_time][j][0]  # in km
                        y1 = sat_cbf[cur_time][j][1]
                        z1 = sat_cbf[cur_time][j][2]
                        dist = math.sqrt(
                            np.square(x1 - x2) + np.square(y1 - y2) +
                            np.square(z1 - z2))
                        if dist < bound_dis:
                            # [satellite index，distance]
                            access_list.update({j: dist})
                if len(access_list) > antenna_num:
                    sorted_access_list = dict(
                        sorted(access_list.items(), key=lambda item: item[1]))
                    cnt = 0
                    for key, value in sorted_access_list.items():
                        cnt = cnt + 1
                        if cnt > antenna_num:
                            break
                        delay_time = value / (17.31 / 29.5 *
                                              299792.458) * 1000  # ms
                        delay_matrix[sat_num + i][key] = delay_time
                        delay_matrix[key][sat_num + i] = delay_time
                elif len(access_list) != 0:
                    for key, value in access_list.items():
                        delay_time = value / (17.31 / 29.5 *
                                              299792.458) * 1000  # ms
                        delay_matrix[sat_num + i][key] = delay_time
                        delay_matrix[key][sat_num + i] = delay_time
            for i in range(num_orbits):
                for j in range(num_sats_per_orbit):
                    num_sat1 = i * num_sats_per_orbit + j
                    x1 = sat_cbf[cur_time][num_sat1][0]  # km
                    y1 = sat_cbf[cur_time][num_sat1][1]
                    z1 = sat_cbf[cur_time][num_sat1][2]
                    num_sat2 = i * num_sats_per_orbit + (
                        j + 1) % num_sats_per_orbit
                    x2 = sat_cbf[cur_time][num_sat2][0]  # km
                    y2 = sat_cbf[cur_time][num_sat2][1]
                    z2 = sat_cbf[cur_time][num_sat2][2]
                    num_sat3 = ((i + 1) % num_orbits) * num_sats_per_orbit + j
                    x3 = sat_cbf[cur_time][num_sat3][0]  # km
                    y3 = sat_cbf[cur_time][num_sat3][1]
                    z3 = sat_cbf[cur_time][num_sat3][2]
                    delay1 = math.sqrt(
                        np.square(x1 - x2) + np.square(y1 - y2) +
                        np.square(z1 - z2)) / (17.31 / 29.5 *
                                               299792.458) * 1000  # ms
                    delay2 = math.sqrt(
                        np.square(x1 - x3) + np.square(y1 - y3) +
                        np.square(z1 - z3)) / (17.31 / 29.5 *
                                               299792.458) * 1000  # ms
                    delay_matrix[num_sat1][num_sat2] = delay1
                    delay_matrix[num_sat2][num_sat1] = delay1
                    delay_matrix[num_sat1][num_sat3] = delay2
                    delay_matrix[num_sat3][num_sat1] = delay2
            np.savetxt(path + "/delay/" + str(cur_time + 1) + ".txt",
                       delay_matrix,
                       fmt='%.2f',
                       delimiter=',')
            for i in range(len(delay_matrix)):
                delay_matrix[i, ...] = 0

    def to_cbf(self, lat_long,
               length):  # the xyz coordinate system. length: number of nodes
        cbf = []
        radius = 6371
        for num in range(0, length):
            cbf_in = []
            z = radius * math.sin(math.radians(float(lat_long[num][0])))
            x = radius * math.cos(math.radians(float(
                lat_long[num][0]))) * math.cos(
                    math.radians(float(lat_long[num][1])))
            y = radius * math.cos(math.radians(float(
                lat_long[num][0]))) * math.sin(
                    math.radians(float(lat_long[num][1])))
            cbf_in.append(x)
            cbf_in.append(y)
            cbf_in.append(z)
            cbf.append(cbf_in)
        return cbf  # xyz coordinates of all the satellites

    def calculate_bound(self, inclination_angle, height):
        bound_distance = 6371 * math.cos(
            (90 + inclination_angle) / 180 * math.pi) + math.sqrt(
                math.pow(
                    6371 * math.cos(
                        (90 + inclination_angle) / 180 * math.pi), 2) +
                math.pow(height, 2) + 2 * height * 6371)
        return bound_distance

    def matrix_to_change(self, duration, orbit_number, sat_number, path,
                         GS_lat_long):
        no_fac = len(GS_lat_long)
        no_geo = 0
        duration = duration - 1
        no_leo = orbit_number * sat_number

        topo_duration = [[[0 for i in range(no_leo + no_geo + no_fac)]
                          for i in range(no_leo + no_geo + no_fac)]
                         for k in range(duration)]
        for time in range(1, duration + 1):
            topo_path = path + '/delay/' + str(time) + ".txt"
            adjacency_matrix = sn_get_param(topo_path)
            for i in range(len(adjacency_matrix)):
                for j in range(len(adjacency_matrix[i])):
                    if float(adjacency_matrix[i][j]) > 0:
                        adjacency_matrix[i][j] = 1
                    else:
                        adjacency_matrix[i][j] = 0
            topo_duration[time - 1] = adjacency_matrix

        changetime = []
        Duration = []
        for i in range(duration - 1):
            l1 = topo_duration[i]
            l2 = topo_duration[i + 1]
            if l1 == l2:
                continue
            else:
                changetime.append(i)
        pretime = 0
        for item in changetime:
            Duration.append(item - pretime)
            pretime = item
        Duration.append(60)

        topo_leo_change_path = path + "/Topo_leo_change.txt"
        f = open(topo_leo_change_path, "w")
        cnt = 1
        for i in range(duration - 1):
            pre_lines = topo_duration[i]
            now_lines = topo_duration[i + 1]
            if pre_lines == now_lines:
                continue
            else:
                f.write("time " + str(i + 2) + ":\n")  # time started from 1
                f.write('duration ' + str(Duration[cnt]) + ":\n")
                cnt += 1
                f.write("add:\n")
                for j in range(no_fac):
                    prelines = pre_lines[no_geo + no_leo + j]
                    nowlines = now_lines[no_geo + no_leo + j]
                    for k in range(no_geo + no_leo + no_fac):
                        if prelines[k] == 0 and nowlines[k] == 1:
                            f.write(
                                str(k + 1) + "-" + str(no_leo + j + 1) +
                                "\n")  # index
                f.write("del:\n")
                for j in range(no_fac):
                    prelines = pre_lines[no_geo + no_leo + j]
                    nowlines = now_lines[no_geo + no_leo + j]
                    for k in range(no_geo + no_leo + no_fac):
                        if prelines[k] == 1 and nowlines[k] == 0:
                            f.write(
                                str(k + 1) + "-" + str(no_leo + j + 1) +
                                "\n")  # index
        f.write("time " + str(self.duration) + ":\n")  #
        f.write("end of the emulation! \n")  #
        f.close()
        cnt = 1

    def calculate_delay(self):
        path = self.configuration_file_path + "/" + self.file_path
        sat_cbf = [
        ]  # first dimension: time. second dimension: node. third dimension: xyz
        sat_lla = [
        ]  # first dimension: time. second dimension: node. third dimension: lla
        fac_cbf = []  # first dimension: node. second dimension: xyz

        if os.path.exists(path + '/delay') == True:
            osstr = "rm -f " + path + "/delay/*"
            os.system(osstr)
        else:
            os.system("mkdir " + path)
            os.system("mkdir " + path + "/delay")
        if os.path.exists(path + '/position') == True:
            osstr = "rm -f " + path + "/position/*"
            os.system(osstr)
        else:
            os.system("mkdir " + path + "/position")

        ts = load.timescale()
        since = datetime(1949, 12, 31, 0, 0, 0)
        start = datetime(2020, 1, 1, 0, 0, 0)
        epoch = (start - since).days
        inclination = self.inclination * 2 * np.pi / 360
        GM = 3.9860044e14
        R = 6371393
        altitude = self.satellite_altitude * 1000
        mean_motion = np.sqrt(GM / (R + altitude)**3) * 60
        num_of_orbit = self.orbit_number
        sat_per_orbit = self.sat_number
        num_of_sat = num_of_orbit * sat_per_orbit
        F = 18
        bound_dis = self.calculate_bound(
            self.antenna_inclination, self.satellite_altitude) * 29.5 / 17.31

        duration = self.duration  # second
        result = [[] for i in range(duration)]  # LLA result
        lla_per_sec = [[] for i in range(duration)]  # LLA result

        for i in range(num_of_orbit):  # range(num_of_orbit)
            raan = i / num_of_orbit * 2 * np.pi
            for j in range(sat_per_orbit):  # range(sat_per_orbit)
                mean_anomaly = (j * 360 / sat_per_orbit + i * 360 * F /
                                num_of_sat) % 360 * 2 * np.pi / 360
                satrec = Satrec()
                satrec.sgp4init(
                    WGS84,  # gravity model
                    'i',  # 'a' = old AFSPC mode, 'i' = improved mode
                    i * sat_per_orbit + j,  # satnum: Satellite number
                    epoch,  # epoch: days since 1949 December 31 00:00 UT
                    2.8098e-05,  # bstar: drag coefficient (/earth radii)
                    6.969196665e-13,  # ndot: ballistic coefficient (revs/day)
                    0.0,  # nddot: second derivative of mean motion (revs/day^3)
                    0.001,  # ecco: eccentricity
                    0.0,  # argpo: argument of perigee (radians)
                    inclination,  # inclo: inclination (radians)
                    mean_anomaly,  # mo: mean anomaly (radians)
                    mean_motion,  # no_kozai: mean motion (radians/minute)
                    raan,  # nodeo: right ascension of ascending node (radians)
                )
                sat = EarthSatellite.from_satrec(satrec, ts)
                cur = datetime(2022, 1, 1, 1, 0, 0)
                t_ts = ts.utc(*cur.timetuple()[:5],
                              range(duration))  # [:4]:minute，[:5]:second
                geocentric = sat.at(t_ts)
                subpoint = wgs84.subpoint(geocentric)
                # list: [subpoint.latitude.degrees] [subpoint.longitude.degrees] [subpoint.elevation.km]
                for t in range(duration):
                    lla = '%f,%f,%f\n' % (subpoint.latitude.degrees[t],
                                          subpoint.longitude.degrees[t],
                                          subpoint.elevation.km[t])
                    result[t].append(lla)
                    lla = []
                    lla.append(subpoint.latitude.degrees[t])
                    lla.append(subpoint.longitude.degrees[t])
                    lla.append(subpoint.elevation.km[t])
                    lla_per_sec[t].append(lla)

        for t in range(duration):
            file = path + '/position/' + '%d.txt' % t
            with open(file, 'w') as fw:
                fw.writelines(result[t])
            cbf_per_sec = self.to_cbf(lla_per_sec[t], num_of_sat)
            sat_cbf.append(cbf_per_sec)
            sat_lla.append(lla_per_sec[t])

        if len(self.GS_lat_long) != 0:
            fac_cbf = self.to_cbf(self.GS_lat_long, len(self.GS_lat_long))

        alpha = np.degrees(
            np.arccos(6371 / (6371 + self.satellite_altitude) *
                      np.cos(np.radians(inclination)))) - inclination
        self.access_P_L_shortest(sat_cbf, fac_cbf, len(self.GS_lat_long),
                                 self.sat_number * self.orbit_number,
                                 self.orbit_number, self.sat_number,
                                 self.duration, self.GS_lat_long, sat_lla,
                                 bound_dis, alpha, self.antenna_number, path)
        self.matrix_to_change(self.duration, self.orbit_number,
                              self.sat_number, path, self.GS_lat_long)

    def compute_conf(self, sat_node_number, interval, num1, num2, ID, Q,
                     num_backbone, matrix):
        Q.append(
            "log \"/var/log/bird.log\" { debug, trace, info, remote, warning, error, auth, fatal, bug };"
        )
        Q.append("debug protocols all;")
        Q.append("protocol device {")
        Q.append("}")
        Q.append(" protocol direct {")
        Q.append("    disabled;		# Disable by default")
        Q.append("    ipv4;			# Connect to default IPv4 table")
        Q.append("    ipv6;			# ... and to default IPv6 table")
        Q.append("}")
        Q.append("protocol kernel {")
        Q.append("    ipv4 {			# Connect protocol to IPv4 table by channel")
        Q.append(
            "        export all;	# Export to protocol. default is export none")
        Q.append("    };")
        Q.append("}")
        # Q.append("protocol kernel {")
        # Q.append("    ipv6 { export all; ")
        # Q.append("    };")
        # Q.append("}")
        Q.append("protocol static {")
        Q.append("    ipv4;			# Again, IPv6 channel with default options")
        Q.append("}")
        Q.append("protocol ospf{")
        Q.append("    ipv4 {")
        Q.append("        import all;")
        Q.append("    };")
        Q.append("    area 0 {")
        Q.append("    interface \"B%d-eth0\" {" % ID)
        Q.append("        type broadcast;		# Detected by default")
        Q.append("        cost 256;")
        Q.append("        hello " + str(interval) +
                 ";			# Default hello perid 10 is too long")
        Q.append("    };")
        Q.append("    interface \"inter_machine\" {")
        Q.append("        type broadcast;		# Detected by default")
        Q.append("        cost 256;")
        Q.append("        hello " + str(interval) +
                 ";			# Default hello perid 10 is too long")
        Q.append("    };")
        if num1 <= sat_node_number and num2 <= num_backbone and ID <= sat_node_number:  # satellite
            for peer in range(num1, num2 + 1):
                if (peer == ID) or (int(float(matrix[ID - 1][peer - 1])) == 0):
                    continue
                Q.append("    interface \"B%d-eth%d\" {" % (ID, peer))
                Q.append("        type broadcast;		# Detected by default")
                Q.append("        cost 256;")
                Q.append("        hello " + str(interval) +
                         ";			# Default hello perid 10 is too long")
                Q.append("    };")
            if num2 > sat_node_number:
                for i in range(sat_node_number + 1,
                               num_backbone + 1):  # each ground station
                    Q.append("    interface \"B%d-eth%d\" {" % (ID, i))
                    Q.append("        type broadcast;		# Detected by default")
                    Q.append("        cost 256;")
                    Q.append("        hello " + str(interval) +
                             ";			# Default hello perid 10 is too long")
                    Q.append("    };")
        elif num1 <= sat_node_number and num2 <= num_backbone and ID > sat_node_number:  # ground station
            for peer in range(1,
                              1 + sat_node_number):  # fac and each satellite
                Q.append("    interface \"B%d-eth%d\" {" % (ID, peer))
                Q.append("        type broadcast;		# Detected by default")
                Q.append("        cost 256;")
                Q.append("        hello " + str(interval) +
                         ";			# Default hello perid 10 is too long")
                Q.append("    };")
            Q.append("    interface \"B%d-default\" {" % (ID))
            Q.append("        type broadcast;		# Detected by default")
            Q.append("        cost 256;")
            Q.append("        hello " + str(interval) +
                     ";			# Default hello perid 10 is too long")
            Q.append("    };")
        elif num1 > num_backbone and num2 > num_backbone:  # ground users
            if ID != num1 and ID != num2:
                Q.append("    interface \"B%d-eth%d\" {" % (ID, ID - 1))
                Q.append("        type broadcast;		# Detected by default")
                Q.append("        cost 256;")
                Q.append("        hello " + str(interval) +
                         ";			# Default hello perid 10 is too long")
                Q.append("    };")
                Q.append("    interface \"B%d-eth%d\" {" % (ID, ID + 1))
                Q.append("        type broadcast;		# Detected by default")
                Q.append("        cost 256;")
                Q.append("        hello " + str(interval) +
                         ";			# Default hello perid 10 is too long")
                Q.append("    };")
            elif ID == num1:
                Q.append("    interface \"B%d-eth%d\" {" % (ID, ID + 1))
                Q.append("        type broadcast;		# Detected by default")
                Q.append("        cost 256;")
                Q.append("        hello " + str(interval) +
                         ";			# Default hello perid 10 is too long")
                Q.append("    };")
            elif ID == num2:
                Q.append("    interface \"B%d-eth%d\" {" % (ID, ID - 1))
                Q.append("        type broadcast;		# Detected by default")
                Q.append("        cost 256;")
                Q.append("        hello " + str(interval) +
                         ";			# Default hello perid 10 is too long")
                Q.append("    };")
        else:
            return False
        Q.append("    };")
        Q.append(" }")
        return True

    def print_conf(self, sat_node_number, fac_node_number, ID, Q, remote_ftp):
        filename = self.file_path + "/conf/bird-" + \
            str(sat_node_number) + "-" + str(fac_node_number) + "/B%d.conf" % ID
        fout = open(self.configuration_file_path + "/" + filename, 'w+')
        for item in Q:
            fout.write(str(item) + "\n")
        fout.close()
        remote_ftp.put(self.configuration_file_path + "/" + filename, filename)

    def generate_conf(self, remote_ssh, remote_ftp):
        if self.intra_routing != "OSPF" and self.intra_routing != "ospf":
            return False
        if os.path.exists(self.configuration_file_path + "/" + self.file_path +
                          "/conf/bird-" +
                          str(self.orbit_number * self.sat_number) + "-" +
                          str(len(self.GS_lat_long))) == True:
            osstr = "rm -f " + self.configuration_file_path+"/"+self.file_path+"/conf/bird-" + \
                str(self.orbit_number*self.sat_number) + "-" + str(len(self.GS_lat_long)) + "/*"
            os.system(osstr)
            sn_remote_cmd(remote_ssh, "mkdir ~/" + self.file_path + "/conf")
            sn_remote_cmd(
                remote_ssh, "mkdir ~/" + self.file_path + "/conf/bird-" +
                str(self.orbit_number * self.sat_number) + "-" +
                str(len(self.GS_lat_long)))
        else:
            os.makedirs(self.configuration_file_path + "/" + self.file_path +
                        "/conf/bird-" +
                        str(self.orbit_number * self.sat_number) + "-" +
                        str(len(self.GS_lat_long)))
            sn_remote_cmd(remote_ssh, "mkdir ~/" + self.file_path + "/conf")
            sn_remote_cmd(
                remote_ssh, "mkdir ~/" + self.file_path + "/conf/bird-" +
                str(self.orbit_number * self.sat_number) + "-" +
                str(len(self.GS_lat_long)))
        path = self.configuration_file_path + "/" + self.file_path + "/delay/1.txt"
        matrix = sn_get_param(path)
        num_backbone = self.orbit_number * self.sat_number + len(
            self.GS_lat_long)
        error = True
        for i in range(len(self.AS)):
            if len(self.AS[i]) != 1:
                for ID in range(self.AS[i][0], self.AS[i][1] + 1):
                    Q = []
                    error = self.compute_conf(
                        self.orbit_number * self.sat_number,
                        self.hello_interval, self.AS[i][0], self.AS[i][1], ID,
                        Q, num_backbone, matrix)
                    self.print_conf(self.orbit_number * self.sat_number,
                                    len(self.GS_lat_long), ID, Q, remote_ftp)
            else:  # one node in one AS
                ID = self.AS[i][0]
                Q = []
                Q.append(
                    "log \"/var/log/bird.log\" { debug, trace, info, remote, warning, error, auth, fatal, bug };"
                )
                Q.append("debug protocols all;")
                Q.append("protocol device {")
                Q.append("}")
                Q.append(" protocol direct {")
                Q.append("    disabled;		# Disable by default")
                Q.append("    ipv4;			# Connect to default IPv4 table")
                Q.append("    ipv6;			# ... and to default IPv6 table")
                Q.append("}")
                Q.append("protocol kernel {")
                Q.append(
                    "    ipv4 {			# Connect protocol to IPv4 table by channel")
                Q.append(
                    "        export all;	# Export to protocol. default is export none"
                )
                Q.append("    };")
                Q.append("}")
                Q.append("protocol static {")
                Q.append(
                    "    ipv4;			# Again, IPv6 channel with default options")
                Q.append("}")
                Q.append("protocol ospf {")
                Q.append("    ipv4 {")
                Q.append("        import all;")
                Q.append("    };")
                Q.append("    area 0 {")
                Q.append("    interface \"B%d-eth0\" {" % ID)
                Q.append("        type broadcast;		# Detected by default")
                Q.append("        cost 256;")
                Q.append("        hello " + str(self.hello_interval) +
                         ";			# Default hello perid 10 is too long")
                Q.append("    };")
                Q.append("    interface \"inter_machine\" {")
                Q.append("        type broadcast;		# Detected by default")
                Q.append("        cost 256;")
                Q.append("        hello " + str(interval) +
                         ";			# Default hello perid 10 is too long")
                Q.append("    };")
                Q.append("    };")
                Q.append(" }")
                self.print_conf(self.orbit_number * self.sat_number,
                                len(self.GS_lat_long), ID, Q, remote_ftp)

        return error
