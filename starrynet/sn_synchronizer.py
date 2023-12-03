#!/usr/bin/python
# -*- coding: UTF-8 -*-
"""
StarryNet: empowering researchers to evaluate futuristic integrated space and terrestrial networks.
author: Zeqi Lai (zeqilai@tsinghua.edu.cn) and Yangtao Deng (dengyt21@mails.tsinghua.edu.cn)
"""
import time
import threading
import zipfile
from starrynet.sn_observer import *
from starrynet.sn_utils import *

ASSIGN_FILENAME = 'assign.txt'

BIRD_CONF_TEXT = """\
log "/var/log/bird.log" { warning, error, auth, fatal, bug };
protocol device {
}
protocol direct {
    disabled;       # Disable by default
    ipv4;           # Connect to default IPv4 table
    ipv6;           # ... and to default IPv6 table
}
protocol kernel {
    ipv4 {          # Connect protocol to IPv4 table by channel
        export all; # Export to protocol. default is export none
    };
}
# protocol static {
#     ipv4;           # Again, IPv6 channel with default options
# }
protocol ospf{
    ipv4 {
        import all;
    };
    area 0 {
    interface "*-SH*O*S*" {
        type broadcast; # Detected by default
        cost 256;
        hello 5;        # Default hello perid 10 is too long
    };
    interface "*-GS*" {
        type broadcast; # Detected by default
        cost 256;
        hello 5;        # Default hello perid 10 is too long
    };
    interface "B*-default" {
        type broadcast; # Detected by default
        cost 256;
        hello 10;        # Default hello perid 10 is too long
    };
    };
}
"""

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
        sn_remote_cmd(self.ssh, 'mkdir ~/' + experiment_name)
        self.dir = sn_remote_cmd(self.ssh, 'echo ~/' + experiment_name)
        self.sftp.put(
            os.path.join(os.path.dirname(__file__), 'sn_orchestrater.py'),
            self.dir + '/sn_orchestrater.py'
        )
        self.sftp.put(
            os.path.join(self.local_dir, 'bird.conf'),
            self.dir + '/bird.conf'
        )
        # self.sftp.put(
        #     os.path.join(self.local_dir, 'pyctr.so'),
        #     self.dir + '/pyctr.so'
        # )
        self.sftp.put(
            os.path.join(self.local_dir, ASSIGN_FILENAME),
            self.dir + '/' + ASSIGN_FILENAME
        )

    def init_nodes(self):
        sn_remote_wait_output(
            self.ssh,
            f"python3 {self.dir}/sn_orchestrater.py {self.id} nodes {self.dir}"
        )
    
    def init_network(self, isl_bw, isl_loss, gsl_bw, gsl_loss):
        for shell in self.shell_lst:
            rmt_path = f"{self.dir}/{shell['name']}.zip"
            rmt_f = self.sftp.open(rmt_path, "wb")
            zip_f = zipfile.ZipFile(rmt_f, mode='w')
            pattern = os.path.join(self.local_dir, shell['name'], 'isl', '*.txt')
            for isl_txt in glob.glob(pattern):
                zip_f.write(isl_txt, f"{shell['name']}/{os.path.basename(isl_txt)}")
            zip_f.close()
            rmt_f.close()
            sn_remote_cmd(self.ssh, f"python3 -m zipfile -e {rmt_path} {self.dir}")
        if self.gs_dirname:
            rmt_path = f"{self.dir}/{self.gs_dirname}.zip"
            rmt_f = self.sftp.open(rmt_path, "wb")
            zip_f = zipfile.ZipFile(rmt_f, mode='w')
            pattern = os.path.join(self.local_dir, self.gs_dirname, 'gsl', '*.txt')
            for gsl_txt in glob.glob(pattern):
                zip_f.write(
                    gsl_txt,
                    f"{self.gs_dirname}/{os.path.basename(gsl_txt)}"
                )
            zip_f.close()
            rmt_f.close()
            sn_remote_cmd(self.ssh, f"python3 -m zipfile -e {rmt_path} {self.dir}")
        self.update_network(0, isl_bw, isl_loss, gsl_bw, gsl_loss)

    def update_network(self, t, isl_bw, isl_loss, gsl_bw, gsl_loss):
        sn_remote_wait_output(
            self.ssh,
            f"python3 {self.dir}/sn_orchestrater.py {self.id} networks {self.dir} "
            f"{t} {isl_bw} {isl_loss} {gsl_bw} {gsl_loss}"
        )
    
    def init_routed(self):
        print(sn_remote_cmd(
            self.ssh,
            f"python3 {self.dir}/sn_orchestrater.py {self.id} routed {self.dir}"
        ))
    
    def ping_async(self, res_path, src, dst):
        def _ping_inner(ssh, dir, res_path, src, dst):
            output = sn_remote_cmd(
                ssh,
                f"python3 {dir}/sn_orchestrater.py {self.id} ping {dir} "
                f"{src[0]} {src[1]} {src[2]} {dst[0]} {dst[1]} {dst[2]}"
            )
            with open(res_path, 'w') as f:
                f.write(output)
        thread = threading.Thread(
            target=_ping_inner,
            args=(self.ssh, self.dir, res_path, src, dst)
        )
        thread.start()
        return thread
    
    def perf_async(self, src, dst):
        thread = threading.Thread(
            target=sn_remote_cmd,
            args=(self.ssh,
                  f"python3 {self.dir}/sn_orchestrater.py {self.id} perf {self.dir} "
                  f"{src[0]} {src[1]} {src[2]} {dst[0]} {dst[1]} {dst[2]}"),
        )
        thread.start()
        return thread

    def clean(self):
        sn_remote_cmd(
            self.ssh,
            f"python3 {self.dir}/sn_orchestrater.py {self.id} clean {self.dir}"
        )

class StarryNet():

    def __init__(self, configuration_file_path, GS_lat_long):
        # Initialize constellation information.
        sn_args = sn_load_file(configuration_file_path)
        self.shell_lst = sn_args.shell_lst
        self.gs_lat_long = GS_lat_long
        self.link_style = sn_args.link_style
        self.link_policy = sn_args.link_policy
        self.IP_version = sn_args.IP_version
        self.step = sn_args.step
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
            self.local_dir, self.duration, self.step, self.shell_lst, self.link_style,
            self.gs_lat_long, self.antenna_number, self.elevation, self.link_policy
        )
        (self.remote_lst,
         self.sat_mid_lst, self.gs_mid) = self._assign_remote(sn_args.machine_lst)

        self.utility_checking_time = []
        self.route_checking_events = []
        self.ping_events = []
        self.perf_events = []
        self.sr_events = []
        self.damage_events = []
        self.damage_list = []
        self.recovery_events = []
    
    def _init_local(self):
        for txt_file in glob.glob(os.path.join(self.local_dir, '*.txt')):
            os.remove(txt_file)
        for shell in self.shell_lst:
            os.makedirs(os.path.join(self.local_dir, shell['name']), exist_ok=True)
        os.makedirs(os.path.join(self.local_dir, self.gs_dirname), exist_ok=True)
        with open(os.path.join(self.local_dir, 'bird.conf'), 'w') as f:
            f.write(BIRD_CONF_TEXT)

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

            shell_id = 0
            sat_mid_lst = []
            assigned_shell_lst = []
            for i, remote in enumerate(machine_lst):
                shell_num = shell_per_machine
                if i < remainder:
                    shell_num += 1
                assigned_shells = [
                    self.shell_lst[j] for j in range(shell_id, shell_id + shell_num)
                ]
                # all satellites of a shell assigned to a single machine
                sat_mid_lst.extend([
                    (i,) * shell['sat'] for shell in assigned_shells
                ])
                assigned_shell_lst.append(assigned_shells)
                shell_id += shell_num
            gs_mid = []
            # TODO: better ground station assign
            with open(os.path.join(self.local_dir, self.gs_dirname,'gsl','0.txt'))as f:
                for line in f:
                    line = line.strip()
                    if len(line) == 0:
                        continue
                    init = line.split('|')[3]
                    if len(init) == 0:
                        gs_mid.append(0)
                        continue
                    gsl = init.split(' ')[0].split(',')
                    shell_id, sid = int(gsl[1]), int(gsl[3])
                    mid = sat_mid_lst[shell_id][sid]
                    gs_mid.append(mid)
            with open(os.path.join(self.local_dir, ASSIGN_FILENAME), 'w') as f:
                f.write(' '.join(str(mid) for mid in gs_mid) + '\n')
                # every shell
                for sat_mid, shell in zip(sat_mid_lst, self.shell_lst):
                    f.write(
                        str(shell['orbit']) + ' ' + shell['name'] + '\n'
                        + ' '.join(str(mid) for mid in sat_mid) + '\n'
                    )
                f.write('\n')
                for remote in machine_lst:
                    f.write(remote['IP'] + '\n')

        for i, remote in enumerate(machine_lst):
            remote_lst.append(RemoteMachine(
                i,
                remote['IP'],
                remote['port'],
                remote['username'],
                remote['password'],
                assigned_shell_lst[i],
                self.experiment_name,
                self.local_dir,
                self.gs_dirname if i in gs_mid else None
                )
            )
        return remote_lst, sat_mid_lst, gs_mid

    def create_nodes(self):
        print('Initializing nodes ...')
        begin = time.time()
        for remote in self.remote_lst:
            remote.init_nodes()
        print("Node initialization:", time.time() - begin, "s consumed.")

    def create_links(self):
        print('Initializing links ...')
        thread_lst = []
        begin = time.time()
        for remote in self.remote_lst:
            thread = threading.Thread(
                target=remote.init_network,
                args=(self.sat_bandwidth,
                      self.sat_loss,
                      self.sat_ground_bandwidth,
                      self.sat_ground_loss),
            )
            thread.start()
            thread_lst.append(thread)
        for thread in thread_lst:
            thread.join()
        print("Link initialization:", time.time() - begin, 's consumed.')

    def run_routing_deamon(self):
        print('Initializing routing ...')
        for remote in self.remote_lst:
            remote.init_routed()
        print("Routing daemon initialized. Wait 30s for route converged")
        for i in range(30):
            print(f'\r{i} / 30', end=' ')
            time.sleep(1)
        print("Routing started!")

    def get_distance(self, shell1, orbit1, sat1, shell2, orbit2, sat2, t):
        raise NotImplementedError

    def get_neighbors(self, sat_index, time_index):
        raise NotImplementedError

    def get_GSes(self, sat_index, time_index):
        raise NotImplementedError

    def get_utility(self, time_index):
        self.utility_checking_time.append(time_index)

    def get_position(self, shell1, orbit1, sat1, time_index):
        path = self.local_dir + '/position/%d.txt' % time_index
        f = open(path)
        ADJ = f.readlines()
        f.close()
        return ADJ[sat_index - 1]

    def get_IP(self, sat_index):
        raise NotImplementedError

    def set_damage(self, damaging_ratio, t):
        self.damage_events.append((t, damaging_ratio))

    def set_recovery(self, t):
        self.recovery_events.append(t)

    def check_routing_table(self, sat_index, t):
        self.route_checking_events.append((t, sat_index))

    def set_next_hop(self,
            src_shell, src_orbit, src_sat,
            des_shell, des_orbit, des_sat,
            nxt_shell, nxt_orbit, nxt_sat, t
        ):
        self.sr_events.append(
            (t,
             (src_shell, src_orbit, src_sat),
             (des_shell, des_orbit, des_sat),
             (nxt_shell, nxt_orbit, nxt_sat))
        )

    def set_ping(self, shell1, orbit1, sat1, shell2, orbit2, sat2, t):
        self.ping_events.append(
            (t, (shell1-1, orbit1-1, sat1-1), (shell2-1, orbit2-1, sat2-1))
        )

    def set_perf(self, shell1, orbit1, sat1, shell2, orbit2, sat2, t):
        self.perf_events.append(
            (t, (shell1-1, orbit1-1, sat1-1), (shell2-1, orbit2-1, sat2-1))
        )
    
    def event(self, t):
        while len(self.ping_events) > 0 and self.ping_events[-1][0] <= t:
            ping_event = self.ping_events.pop(-1)
            src_shell, src_sid = ping_event[1][0], ping_event[1][2]
            machine = self.remote_lst[self.sat_mid_lst[src_shell][src_sid]]
            self.ping_threads.append(machine.ping_async(
                os.path.join(
                    self.local_dir, f'{t}-ping-{ping_event[1]}-{ping_event[2]}.txt'),
                ping_event[1],
                ping_event[2]
            ))
        while len(self.perf_events) > 0 and self.perf_events[-1][0] <= t:
            perf_event = self.perf_events.pop(-1)
            machine = self.remote_lst[self.sat_mid_lst[perf_event[1][0]]]
            self.perf_threads.append(machine.perf_async(
                perf_event[1],
                perf_event[2]
            ))
        # TODO: other events

    def start_emulation(self):
        self.ping_events.sort(key=lambda x:x[0], reverse=True)
        self.perf_events.sort(key=lambda x:x[0], reverse=True)
        self.ping_threads = []
        self.perf_threads = []
        t = 0.0
        tid = 1
        while t < self.duration:
            start = time.time()
            print("Trigger events at", t, "s ...")
            self.event(t)
            print("Update networks ...")
            update_start = time.time()
            if tid < self.duration:
                conn_threads = []
                for remote in self.remote_lst:
                    thread = threading.Thread(
                        target=remote.update_network,
                        args=(tid,
                            self.sat_bandwidth,
                            self.sat_loss,
                            self.sat_ground_bandwidth,
                            self.sat_ground_loss
                    ))
                    thread.start()
                    conn_threads.append(thread)
                for thread in conn_threads:
                    thread.join()
            end = time.time()
            print(end-start, "s elapsed,", end-update_start, "s for network update")
            if end - start < 1:
                print('Sleep', 1 + start - end, 's')
                time.sleep(1 + start - end)
            t += self.step
            tid += 1
        for ping_thread in self.ping_threads:
            ping_thread.join()
        for perf_thread in self.perf_threads:
            perf_thread.join()

    def clean(self):
        print("Removing containers and links...")
        for remote in self.remote_lst:
            remote.clean()
        print("All containers and links remoted.")
