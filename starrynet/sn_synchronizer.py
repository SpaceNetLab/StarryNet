#!/usr/bin/python
# -*- coding: UTF-8 -*-
"""
StarryNet: empowering researchers to evaluate futuristic integrated space and terrestrial networks.
author: Zeqi Lai (zeqilai@tsinghua.edu.cn) and Yangtao Deng (dengyt21@mails.tsinghua.edu.cn)
"""
from starrynet.sn_observer import *
from starrynet.sn_utils import *


class StarryNet():

    def __init__(self,
                 configuration_file_path,
                 GS_lat_long,
                 hello_interval=10,
                 AS=[]):
        # Initialize constellation information.
        sn_args = sn_load_file(configuration_file_path, GS_lat_long)
        self.name = sn_args.cons_name
        self.satellite_altitude = sn_args.satellite_altitude
        self.inclination = sn_args.inclination
        self.orbit_number = sn_args.orbit_number
        self.sat_number = sn_args.sat_number
        self.fac_num = sn_args.fac_num
        self.constellation_size = self.orbit_number * self.sat_number
        self.node_size = self.orbit_number * self.sat_number + sn_args.fac_num
        self.link_style = sn_args.link_style
        self.IP_version = sn_args.IP_version
        self.link_policy = sn_args.link_policy
        self.update_interval = sn_args.update_interval
        self.duration = sn_args.duration
        self.inter_routing = sn_args.inter_routing
        self.intra_routing = sn_args.intra_routing
        self.cycle = sn_args.cycle
        self.time_slot = sn_args.time_slot
        self.sat_bandwidth = sn_args.sat_bandwidth
        self.sat_ground_bandwidth = sn_args.sat_ground_bandwidth
        self.sat_loss = sn_args.sat_loss
        self.sat_ground_loss = sn_args.sat_ground_loss
        self.ground_num = sn_args.ground_num
        self.multi_machine = sn_args.multi_machine
        self.antenna_number = sn_args.antenna_number
        self.antenna_inclination = sn_args.antenna_inclination
        self.container_global_idx = 1
        self.hello_interval = hello_interval
        self.AS = AS
        self.configuration_file_path = os.path.dirname(
            os.path.abspath(configuration_file_path))
        self.file_path = './' + sn_args.cons_name + '-' + str(
            sn_args.orbit_number) + '-' + str(sn_args.sat_number) + '-' + str(
                sn_args.satellite_altitude) + '-' + str(
                    sn_args.inclination
                ) + '-' + sn_args.link_style + '-' + sn_args.link_policy
        self.observer = Observer(self.file_path, self.configuration_file_path,
                                 self.inclination, self.satellite_altitude,
                                 self.orbit_number, self.sat_number,
                                 self.duration, self.antenna_number,
                                 GS_lat_long, self.antenna_inclination,
                                 self.intra_routing, self.hello_interval,
                                 self.AS)
        self.docker_service_name = 'constellation-test'
        self.isl_idx = 0
        self.ISL_hub = 'ISL_hub'
        self.container_id_list = []
        self.n_container = 0
        # Get ssh handler.
        self.remote_ssh, self.transport = sn_init_remote_machine(
            sn_args.remote_machine_IP, sn_args.remote_machine_username,
            sn_args.remote_machine_password)
        if self.remote_ssh is None:
            print('Remote SSH login failure.')
            return
        if self.transport is None:
            print('Remote transport login failure.')
            return
        self.remote_ftp = sn_init_remote_ftp(self.transport)
        if self.remote_ftp is None:
            print('Remote ftp login failure.')
            return
        self.utility_checking_time = []
        self.ping_src = []
        self.ping_des = []
        self.ping_time = []
        self.perf_src = []
        self.perf_des = []
        self.perf_time = []
        self.sr_src = []
        self.sr_des = []
        self.sr_target = []
        self.sr_time = []
        self.damage_ratio = []
        self.damage_time = []
        self.damage_list = []
        self.recovery_time = []
        self.route_src = []
        self.route_time = []

        # Initiate a working directory
        sn_thread = sn_init_directory_thread(self.file_path,
                                             self.configuration_file_path,
                                             self.remote_ssh)
        sn_thread.start()
        sn_thread.join()
        # Initiate a necessary delay and position data for emulation
        self.observer.calculate_delay()
        # Generate configuration file for routing
        self.observer.generate_conf(self.remote_ssh, self.remote_ftp)

    def create_nodes(self):
        # Initialize each machine in multiple threads.
        sn_thread = sn_Node_Init_Thread(self.remote_ssh,
                                        self.docker_service_name,
                                        self.node_size, self.container_id_list,
                                        self.container_global_idx)
        sn_thread.start()
        sn_thread.join()
        self.container_id_list = sn_get_container_info(self.remote_ssh)
        print("Constellation initialization done. " +
              str(len(self.container_id_list)) + " have been created.")

    def create_links(self):
        print("Create Links.")
        isl_thread = sn_Link_Init_Thread(
            self.remote_ssh, self.remote_ftp, self.orbit_number,
            self.sat_number, self.constellation_size, self.fac_num,
            self.file_path, self.configuration_file_path, self.sat_bandwidth,
            self.sat_ground_bandwidth, self.sat_loss, self.sat_ground_loss)
        isl_thread.start()
        isl_thread.join()
        print("Link initialization done.")

    def run_routing_deamon(self):
        routing_thread = sn_Routing_Init_Thread(
            self.remote_ssh, self.remote_ftp, self.orbit_number,
            self.sat_number, self.constellation_size, self.fac_num,
            self.file_path, self.sat_bandwidth, self.sat_ground_bandwidth,
            self.sat_loss, self.sat_ground_loss)
        routing_thread.start()
        routing_thread.join()
        print("Bird routing in all containers are running.")

    def get_distance(self, sat1_index, sat2_index, time_index):
        delaypath = self.configuration_file_path + "/" + self.file_path + '/delay/' + str(
            time_index) + '.txt'
        adjacency_matrix = sn_get_param(delaypath)
        delay = float(adjacency_matrix[sat1_index - 1][sat2_index - 1])
        dis = delay * (17.31 / 29.5 * 299792.458) / 1000  # km
        return dis

    def get_neighbors(self, sat_index, time_index):
        neighbors = []
        delaypath = self.configuration_file_path + "/" + self.file_path + '/delay/' + str(
            time_index) + '.txt'
        adjacency_matrix = sn_get_param(delaypath)
        sats = self.orbit_number * self.sat_number
        for i in range(sats):
            if (float(adjacency_matrix[i][sat_index - 1]) > 0.01):
                neighbors.append(i + 1)
        return neighbors

    def get_GSes(self, sat_index, time_index):
        GSes = []
        delaypath = self.configuration_file_path + "/" + self.file_path + '/delay/' + str(
            time_index) + '.txt'
        adjacency_matrix = sn_get_param(delaypath)
        sats = self.orbit_number * self.sat_number
        for i in range(sats, len(adjacency_matrix)):
            if (float(adjacency_matrix[i][sat_index - 1]) > 0.01):
                GSes.append(i + 1)
        return GSes

    def get_utility(self, time_index):
        self.utility_checking_time.append(time_index)

    def get_position(self, sat_index, time_index):
        path = self.configuration_file_path + "/" + self.file_path + '/position/' + '/%d.txt' % time_index
        f = open(path)
        ADJ = f.readlines()
        return ADJ[sat_index - 1]

    def get_IP(self, sat_index):
        IP_info = sn_remote_cmd(
            self.remote_ssh, "docker inspect" +
            " --format='{{range .NetworkSettings.Networks}}{{.IPAddress}}\n{{end}}'"
            + " ovs_container_" + str(sat_index))
        ip_list = []
        for i in range(len(IP_info) - 2):
            ip_list.append(IP_info[i].split()[0])
        return ip_list

    def set_damage(self, damaging_ratio, time_index):
        self.damage_ratio.append(damaging_ratio)
        self.damage_time.append(time_index)

    def set_recovery(self, time_index):
        self.recovery_time.append(time_index)

    def check_routing_table(self, sat_index, time_index):
        self.route_src.append(sat_index)
        self.route_time.append(time_index)

    def set_next_hop(self, sat_index, des, next_hop_sat, time_index):
        self.sr_src.append(sat_index)
        self.sr_des.append(des)
        self.sr_target.append(next_hop_sat)
        self.sr_time.append(time_index)

    def set_ping(self, sat1_index, sat2_index, time_index):
        self.ping_src.append(sat1_index)
        self.ping_des.append(sat2_index)
        self.ping_time.append(time_index)

    def set_perf(self, sat1_index, sat2_index, time_index):
        self.perf_src.append(sat1_index)
        self.perf_des.append(sat2_index)
        self.perf_time.append(time_index)

    def start_emulation(self):
        # Start emulation in a new thread.
        sn_thread = sn_Emulation_Start_Thread(
            self.remote_ssh, self.remote_ftp, self.sat_loss,
            self.sat_ground_bandwidth, self.sat_ground_loss,
            self.container_id_list, self.file_path,
            self.configuration_file_path, self.update_interval,
            self.constellation_size, self.ping_src, self.ping_des,
            self.ping_time, self.sr_src, self.sr_des, self.sr_target,
            self.sr_time, self.damage_ratio, self.damage_time,
            self.damage_list, self.recovery_time, self.route_src,
            self.route_time, self.duration, self.utility_checking_time,
            self.perf_src, self.perf_des, self.perf_time)
        sn_thread.start()
        sn_thread.join()

    def stop_emulation(self):
        # Stop emulation in a new thread.
        sn_thread = sn_Emulation_Stop_Thread(self.remote_ssh, self.remote_ftp,
                                             self.file_path)
        sn_thread.start()
        sn_thread.join()
