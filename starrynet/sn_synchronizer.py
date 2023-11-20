#!/usr/bin/python
# -*- coding: UTF-8 -*-
"""
StarryNet: empowering researchers to evaluate futuristic integrated space and terrestrial networks.
author: Zeqi Lai (zeqilai@tsinghua.edu.cn) and Yangtao Deng (dengyt21@mails.tsinghua.edu.cn)
"""
import time
import threading
from starrynet.sn_observer import *
from starrynet.sn_utils import *

ASSIGN_FILENAME = 'assign.txt'

class RemoteMachine:
    
    def __init__(self, id, host, port, username, password,
                 shell_lst, experiment_name, local_dir, gs_dirname):
        self.id = id
        self.shell_lst = shell_lst
        self.local_dir = local_dir
        self.gs_dirname = gs_dirname
        self.ssh, self.sftp = sn_connect_remote(
            host = host,
            port = port,
            username = username,
            password = password,
        )
        sn_remote_cmd(self.ssh, f'export MACHINE_ID={self.id}')
        sn_remote_cmd(self.ssh, 'mkdir ~/' + experiment_name)
        self.dir = sn_remote_cmd(self.ssh, 'echo ~/' + experiment_name)
        self.sftp.put(
            os.path.join(os.path.dirname(__file__), 'orchestrater.py'),
            self.dir + '/orchestrater.py'
        )
        
        self.sftp.put(
            os.path.join(os.path.dirname(__file__), 'pyctr.so'),
            self.dir + '/pyctr.so'
        )
        self.sftp.put(
            os.path.join(os.path.dirname(__file__), 'setup.py'),
            self.dir + '/setup.py'
        )
        self.sftp.put(
            os.path.join(self.local_dir, ASSIGN_FILENAME),
            self.dir + '/' + ASSIGN_FILENAME
        )

    def init_nodes(self):
        sn_remote_wait_output(
            self.ssh,
            f"python3 {self.dir}/orchestrater.py {self.id} nodes {self.dir}"
        )
    
    def create_network(self, bw, loss):
        for shell in self.shell_lst:
            self.sftp.put(
                os.path.join(self.local_dir, shell['name'], 'isl', '1.txt'),
                f"{self.dir}/{shell['name']}/1.txt"
            )
            sn_remote_wait_output(
                self.ssh,
                f"python3 {self.dir}/orchestrater.py isls {self.dir}/{shell['name']} "
                f"1.txt {bw} {loss}"
            )
        self.sftp.put(
            os.path.join(self.local_dir, self.gs_dirname, 'GS', '1.txt'),
            f"{self.dir}/{shell['name']}/1.txt"
        )
        sn_remote_wait_output(
            self.ssh,
            f"python3 {self.dir}/orchestrater.py gsls {self.dir}/{self.gs_dirname} "
        )

class StarryNet():

    def __init__(self, configuration_file_path, GS_lat_long):
        # Initialize constellation information.
        sn_args = sn_load_file(configuration_file_path, GS_lat_long)
        self.shell_lst = sn_args.shell_lst
        self.gs_lat_long = GS_lat_long
        self.link_style = sn_args.link_style
        self.link_policy = sn_args.link_policy
        self.IP_version = sn_args.IP_version
        self.update_interval = sn_args.update_interval
        self.duration = sn_args.duration
        self.sat_bandwidth = sn_args.sat_bandwidth
        self.sat_ground_bandwidth = sn_args.sat_ground_bandwidth
        self.sat_loss = sn_args.sat_loss
        self.sat_ground_loss = sn_args.sat_ground_loss
        self.antenna_number = sn_args.antenna_number
        self.elevation = sn_args.antenna_elevation
        self.configuration_dir = os.path.dirname(
            os.path.abspath(configuration_file_path))
        self.experiment_name = sn_args.cons_name\
            +'-'+ sn_args.link_style +'-'+ sn_args.link_policy
        self.gs_dirname = 'GS-' + str(len(self.gs_lat_long))
        for shell_id, shell in enumerate(self.shell_lst):
            shell['name'] = f"{shell_id}_{shell['altitude']}-{shell['inclination']}"\
                            f"-{shell['orbit']}-{shell['sat']}"\
                            f"-{shell['phase_shift']}"

        self.local_dir = os.path.join(self.configuration_dir, self.experiment_name)
        self._init_local()
        # Initiate a necessary delay and position data for emulation
        calculate_delay(
            self.local_dir, self.duration, self.shell_lst, self.link_style,
            self.gs_lat_long, self.antenna_number, self.elevation, self.link_policy
        )
        self.remote_lst = self._assign_remote(sn_args.machine_lst)

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
    
    def _init_local(self):
        for txt_file in glob.glob(os.path.join(self.local_dir, '*.txt')):
            os.remove(txt_file)
        for shell in self.shell_lst:
            os.makedirs(os.path.join(self.local_dir, shell['name']), exist_ok=True)
        os.makedirs(os.path.join(self.local_dir, self.gs_dirname), exist_ok=True)

    def _assign_remote(self, machine_lst):
        # TODO: better partition
        remote_lst = []
        if len(self.shell_lst) * 2 <= len(machine_lst):
            # need intra-shell partition
            machine_per_shell = len(machine_lst) // len(self.shell_lst)
            raise NotImplementedError
        else:
            # only divide shell
            shell_per_machine = len(self.shell_lst) // len(machine_lst)
            remainder = len(self.shell_lst) % len(machine_lst)
            shell_idx = 0
            sat_mask_lst = []
            for i, remote in enumerate(machine_lst):
                shell_num = shell_per_machine
                if i < remainder:
                    shell_num += 1
                assigned_shells = [
                    self.shell_lst[j] for j in range(shell_idx, shell_idx + shell_num)
                ]
                # all satellites of a shell assigned to a single machine
                sat_mask_lst.extend([
                    (i,) * shell['sat'] for shell in assigned_shells
                ])
                shell_idx += shell_num
            with open(os.path.join(self.local_dir, ASSIGN_FILENAME), 'w') as f:
                # TODO: ground station
                f.write(' '.join(str(mid) for mid in []) + '\n')
                # every shell
                for sat_mask, shell in zip(sat_mask_lst, self.shell_lst):
                    f.write(
                        str(shell['orbit']) + ' ' + shell['name'] + '\n'
                        + ' '.join(str(mid) for mid in sat_mask) + '\n'
                    )
            for i, remote in enumerate(machine_lst):
                remote_lst.append(RemoteMachine(
                    i,
                    remote['IP'],
                    remote['port'],
                    remote['username'],
                    remote['password'],
                    self.shell_lst,
                    self.experiment_name,
                    self.local_dir,
                    self.gs_dirname
                    )
                )
        return remote_lst

    def create_nodes(self):
        print('Initializing nodes ...')
        begin = time.time()
        for remote in self.remote_lst:
            remote.init_nodes()
        print("Node initialization:", time.time() - begin, "s consumed.")

    def create_links(self):
        print('Initializing links ...')
        begin = time.time()
        for remote in self.remote_lst:
            remote.create_network()
        print("Link initialization:", time.time() - begin, 's consumed.')

    def run_routing_deamon(self):
        print('Initializing routing ...')
        sn_remote_wait_output(self.remote_ssh,
            f"python3 {self.remote_dir}/orchestrater.py routed {self.remote_dir} ")
        print("Routing daemon initialized. Wait 30s for route converged")
        for i in range(30):
            print(f'\r{i} / 30', end=' ')
            time.sleep(1)
        print("Routing started!")

    def get_distance(self, sat1_index, sat2_index, time_index):
        raise NotImplementedError

    def get_neighbors(self, sat_index, time_index):
        raise NotImplementedError

    def get_GSes(self, sat_index, time_index):
        raise NotImplementedError

    def get_utility(self, time_index):
        self.utility_checking_time.append(time_index)

    def get_position(self, sat_index, time_index):
        path = self.local_dir + '/position/' + '/%d.txt' % time_index
        f = open(path)
        ADJ = f.readlines()
        f.close()
        return ADJ[sat_index - 1]

    def get_IP(self, sat_index):
        raise NotImplementedError

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
    
    def event(self, timeptr):
        if timeptr in self.utility_checking_time:
            sn_check_utility(timeptr, self.remote_ssh, self.local_dir)
        if timeptr % self.update_interval == 0:
            # updating link delays after link changes
            sn_update_delay(self.file_path,
                            self.configuration_dir, timeptr,
                            self.constellation_size,
                            self.remote_ssh, self.remote_ftp)
        if timeptr in self.damage_time:
            sn_damage(
                self.damage_ratio[self.damage_time.index(timeptr)],
                self.damage_list, self.constellation_size,
                self.remote_ssh, self.remote_ftp, self.file_path,
                self.configuration_dir)
        if timeptr in self.recovery_time:
            sn_recover(self.damage_list, self.sat_loss,
                        self.remote_ssh, self.remote_ftp,
                        self.file_path,
                        self.configuration_dir)
        for i, val in enumerate(self.sr_time):
            if val != timeptr:
                continue
            sn_sr(self.sr_src[i],
                    self.sr_des[i],
                    self.sr_target[i],
                    self.container_id_list, self.remote_ssh)
        for i, val in enumerate(self.ping_time):
            if val != timeptr:
                continue
            ping_thread = threading.Thread(
                target=sn_ping,
                args=(self.ping_src[i],
                        self.ping_des[i],
                        self.ping_time[i],
                        self.constellation_size,
                        self.container_id_list,
                        self.file_path,
                        self.configuration_dir,
                        self.remote_ssh))
            ping_thread.start()
            self.ping_threads.append(ping_thread)
        for i, val in enumerate(self.perf_time):
            if val != timeptr:
                continue
            perf_thread = threading.Thread(
                target=sn_perf,
                args=(self.perf_src[i],
                        self.perf_des[i],
                        self.perf_time[i],
                        self.constellation_size,
                        self.container_id_list,
                        self.file_path,
                        self.configuration_dir,
                        self.remote_ssh))
            perf_thread.start()
            self.perf_threads.append(perf_thread)
        for i, val in enumerate(self.route_time):
            if val != timeptr:
                continue
            sn_route(self.route_src[i],
                        self.route_time[i],
                        self.file_path,
                        self.configuration_dir,
                        self.container_id_list, self.remote_ssh)

    def start_emulation(self):
        self.ping_threads = []
        self.perf_threads = []
        timeptr = 2  # current emulating time
        topo_change_file_path = os.path.join(self.local_dir, 'Topo_leo_change.txt')
        fi = open(topo_change_file_path, 'r')
        line = fi.readline()
        while line:  # starting reading change information and emulating
            words = line.split()
            if words[0] == 'time':
                print('Emulation in No.' + str(timeptr) + ' second.')
                # the time when the new change occurrs
                current_time = str(int(words[1][:-1]))
                while int(current_time) > timeptr:
                    start_time = time.time()
                    self.event(timeptr)
                    timeptr += 1
                    end_time = time.time()
                    passed_time = (
                        end_time -
                        start_time) if (end_time - start_time) < 1 else 1
                    time.sleep(1 - passed_time)
                    if timeptr >= self.duration:
                        return
                    print('Emulation in No.' + str(timeptr) + ' second.')
                print("A change in time " + current_time + ':')
                line = fi.readline()
                words = line.split()
                line = fi.readline()
                line = fi.readline()
                words = line.split()
                while words[0] != 'del:':  # addlink
                    word = words[0].split('-')
                    s = int(word[0])
                    f = int(word[1])
                    if s > f:
                        s, f = f, s
                    print("add link", s, f)
                    current_topo_path = self.configuration_dir + "/" + self.file_path + '/delay/' + str(
                        current_time) + '.txt.gz'
                    matrix = sn_get_param(current_topo_path)
                    sn_establish_new_GSL(self.container_id_list, matrix,
                                         self.constellation_size,
                                         self.sat_ground_bw,
                                         self.sat_ground_loss, s, f,
                                         self.remote_ssh)
                    line = fi.readline()
                    words = line.split()
                line = fi.readline()
                words = line.split()
                if len(words) == 0:
                    return
                while words[0] != 'time':  # delete link
                    word = words[0].split('-')
                    s = int(word[0])
                    f = int(word[1])
                    if s > f:
                        s, f = f, s
                    print("del link " + str(s) + "-" + str(f) + "\n")
                    sn_del_link(s, f, self.container_id_list, self.remote_ssh)
                    line = fi.readline()
                    words = line.split()
                    if len(words) == 0:
                        return
                self.event(timeptr)
                timeptr += 1  # current emulating time
                if timeptr >= self.duration:
                    return
        fi.close()
        for ping_thread in self.ping_threads:
            ping_thread.join()
        for perf_thread in self.perf_threads:
            perf_thread.join()

    def stop_emulation(self):
        print("Removing containers...")
        sn_remote_cmd(self.remote_ssh,
            f"python3 {self.remote_dir}/orchestrater.py clean {self.remote_dir}"
        )
