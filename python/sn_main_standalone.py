#!/usr/bin/python
# -*- coding: UTF-8 -*-

"""
StarryNet: empowering researchers to evaluate futuristic integrated space and terrestrial networks.
author: Zeqi Lai (zeqilai@tsinghua.edu.cn)
"""
from sn_utils import *;
import copy





# A thread designed for initializing constellation nodes.
class sn_Constellation_Init_Thread(threading.Thread):
    def __init__(self, remote_ssh, docker_service_name, constellation_size, container_id_list, container_global_idx):
        threading.Thread.__init__(self)
        self.remote_ssh = remote_ssh
        self.docker_service_name = docker_service_name
        self.constellation_size = constellation_size
        self.container_global_idx = container_global_idx
        self.container_id_list = copy.deepcopy(container_id_list)

    def run(self):
        # Reset docker environment.
        sn_reset_docker_env(self.remote_ssh, self.docker_service_name, self.constellation_size)

        # Get container list in each machine.
        self.container_id_list = sn_get_remote_container_info(self.remote_ssh)

        # Rename all containers with the global idx
        sn_rename_all_container(self.remote_ssh, self.container_id_list, self.container_global_idx)


# A thread designed for initializing constellation ISLs.
class sn_ISL_Init_Thread(threading.Thread):
    def __init__(self, remote_ssh, container_id_list, orbit_num, sat_num, constellation_size, isl_idx):
        threading.Thread.__init__(self)
        self.remote_ssh = remote_ssh
        self.constellation_size = constellation_size
        self.container_id_list = copy.deepcopy(container_id_list)
        self.orbit_num = orbit_num
        self.sat_num = sat_num
        self.isl_idx = isl_idx


    def run(self):
        print('Run in ISL init thread.')
        sn_establish_ISLs(self.remote_ssh, self.container_id_list, self.orbit_num, self.sat_num, self.constellation_size, self.isl_idx)



class StarryNet():

    def __init__(self):
        # Initialize constellation information.
        self.orbit_num = 3 # 72
        self.sat_num = 3 # 22
        self.constellation_size = self.orbit_num * self.sat_num
        self.n_container = 0
        self.docker_service_name = 'constellation-test'
        self.isl_idx = 1
        self.ISL_hub = 'ISL_hub'
        self.container_global_idx = 1
        self.ISL_global_idx = 1
        self.container_id_list =[];
        self.conf_path = "/home/ubuntu/Work/Docker/multi_host_remote_control/bird.conf"

        # Get ssh handler.
        self.remote_ssh = sn_init_remote_machine("101.6.21.22", "root", "fit1217")
        if self.remote_ssh is None:
            print('Remote SSH login failure.')
            return

    def init_constellation(self):
        # Initialize each machine in multiple threads.
        sn_thread = sn_Constellation_Init_Thread(self.remote_ssh, self.docker_service_name, self.constellation_size, self.container_id_list, self.container_global_idx)
        sn_thread.start()
        sn_thread.join()
        self.container_id_list = sn_get_remote_container_info(self.remote_ssh)
        print("Constellation initialization done. " + str(len(self.container_id_list)) + " have been created.")


    def init_ISLs(self):
        print("Create ISLs.")
        isl_thread = sn_ISL_Init_Thread(self.remote_ssh, self.container_id_list, self.orbit_num, self.sat_num, self.constellation_size, self.isl_idx)
        isl_thread.start()
        isl_thread.join()
        print("ISL initialization done.")


    def run_routing_deamon(self):
        sn_copy_conf_to_each_container(self.remote_ssh, self.container_id_list, self.conf_path)
        # sn_run_bird_by_container_name(self.remote_ssh, self.container_id_list)


    def create_inter_machine_conn(self):
        # On left machine
        sn_create_inter_machine_connection(self.remote_ssh_left, "ISL_Conn", self.constellation_size - self.sat_num + 1, self.constellation_size, "eth1_data", 1, 10, "255", "10", self.container_id_list_left)
        sn_create_inter_machine_connection(self.remote_ssh_right, "ISL_Conn", self.constellation_size - self.sat_num + 1, self.constellation_size, "eth1_data", 1, 10, "255", "20", self.container_id_list_right)

    def sn_close(self):
        print ("Close StarryNet: " + self.name)


if __name__ == "__main__":
    print('Start StarryNet.')
    sn = StarryNet()
    sn.init_constellation()
    sn.init_ISLs()
    sn.run_routing_deamon()
    #sn.create_inter_machine_conn()




