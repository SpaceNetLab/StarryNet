import os
import json
import argparse
import paramiko
import numpy
import random

def sn_load_file(path):
    f = open(path, 'r', encoding='utf8')
    table = json.load(f)
    parser = argparse.ArgumentParser(description='manual to this script')
    parser.add_argument('--cons_name', type=str, default=table['Name'])
    parser.add_argument('--link_style', type=str, default=table['Satellite link'])
    parser.add_argument('--IP_version', type=str, default=table['IP version'])
    parser.add_argument('--link_policy', type=str, default=table['Link policy'])
    # link delay updating granularity
    parser.add_argument('--step',
                        type=int,
                        default=table['step (s)'])
    parser.add_argument('--duration', type=int, default=table['Duration (s)'])
    parser.add_argument('--sat_bandwidth',
                        type=int,
                        default=table['satellite link bandwidth ("X" Gbps)'])
    parser.add_argument('--sat_ground_bandwidth',
                        type=int,
                        default=table['sat-ground bandwidth ("X" Gbps)'])
    parser.add_argument('--sat_loss',
                        type=int,
                        default=table['satellite link loss ("X"% )'])
    parser.add_argument('--sat_ground_loss',
                        type=int,
                        default=table['sat-ground loss ("X"% )'])
    parser.add_argument('--antenna_number',
                        type=int,
                        default=table['antenna number'])
    parser.add_argument('--antenna_elevation',
                        type=int,
                        default=table['antenna elevation angle'])
    # TODO: parser.add_argument('--handover', default=table["Handover policy"])
    # TODO: parser.add_argument('--time_slot', type=int, default=100)
    # TODO: parser.add_argument('--user_num', type=int, default=0)
    sn_args = parser.parse_args()
    sn_args.__setattr__('machine_lst', table['Machines'])
    shell_lst = [{
        'altitude': shell['Altitude (km)'],
        'inclination': shell['Inclination'],
        'phase_shift': shell['Phase shift'],
        'orbit': shell['Orbits'],
        'sat': shell['Satellites per orbit'],
        } for shell in table["Shells"]]
    sn_args.__setattr__('shell_lst', shell_lst)
    return sn_args

def sn_connect_remote(host, port, username, password):
    remote_ssh = paramiko.SSHClient()
    remote_ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    remote_ssh.connect(hostname=host, port=port, username=username, password=password)
    return remote_ssh, remote_ssh.open_sftp()

def sn_remote_cmd(remote_ssh, cmd):
    return remote_ssh.exec_command(cmd)[1].read().decode().strip()

def sn_remote_wait_output(remote_ssh, cmd):
    for line in remote_ssh.exec_command(cmd, get_pty=True)[1]:
        print(line, end='')

def sn_check_utility(time_index, remote_ssh, local_dir):
    result = sn_remote_cmd(remote_ssh, "vmstat")
    f = open(os.path.join(local_dir, f"utility-info_{time_index}.txt"), "w")
    f.write(result)
    f.close()

def sn_damage(remote_ssh, remote_ftp, remote_dir, local_dir,
              ratio, damage_list, constellation_size):
    print("Randomly setting damaged links...\n")
    cumulated_damage_list = damage_list
    random_list = [
        random.randint(0, constellation_size - 1) 
        for _ in range(int(constellation_size * ratio))
    ]
    cumulated_damage_list.extend(random_list)
    list_file = os.path.join(local_dir, 'mid_files', 'damage_list.txt')
    numpy.savetxt(list_file, random_list)
    remote_ftp.put(list_file, f'{remote_dir}/damage_list.txt')
    sn_remote_cmd(remote_ssh, f"python3 {remote_dir}/orchestrater.py {remote_dir}")
    print("Damage done.\n")


def sn_recover(remote_ssh, remote_ftp, remote_dir, local_dir, damage_list, sat_loss):
    print("Recovering damaged links...\n")
    list_file = os.path.join(local_dir, 'mid_files', 'damage_list.txt')
    numpy.savetxt(list_file, damage_list)
    remote_ftp.put(list_file, f'{remote_dir}/damage_list.txt')
    sn_remote_cmd(remote_ssh, 
        f"python3 {remote_dir}/orchestrater.py {remote_dir} {sat_loss}"
    )
    damage_list.clear()
    print("Link recover done.\n")

def sn_sr(src, des, target, netns_list, remote_ssh):
    ifconfig_output = sn_remote_cmd(remote_ssh, 
        f"ip netns exec {netns_list[des - 1]} "
        r"ifconfig | sed 's/[ \t].*//;/^\(eth0\|\)\(lo\|\)$/d'").splitlines()
    des_IP = sn_remote_cmd(remote_ssh,
        f"ip netns exec {netns_list[des - 1]} ifconfig {ifconfig_output[0][:-1]} " 
        "| awk -F '[ :]+' 'NR==2{print $4}'").splitlines()
    target_IP = sn_remote_cmd(remote_ssh,
        f"ip netns exec {netns_list[target - 1]} ifconfig B{target}-eth{src} "
        "| awk -F '[ :]+' 'NR==2{print $4}'").splitlines()
    sn_remote_cmd(remote_ssh,
        f"ip netns exec {netns_list[src - 1]} "
        f" ip route del {des_IP[0][:-3]}0/24")
    sn_remote_cmd(remote_ssh,
        f"ip netns exec {netns_list[src - 1]} "
        f"ip route add {des_IP[0][:-3]}0/24 dev B{src}-eth{target} via {target_IP[0]}")
    print(
        f"ip netns exec {netns_list[src - 1]} "
        f"ip route add {des_IP[0][:-3]}0/24 dev B{src}-eth{target} via {target_IP[0]}"
    )

def sn_perf(src, des, time_index, constellation_size, container_id_list,
            file_path, configuration_file_path, remote_ssh):
    if des <= constellation_size:
        ifconfig_output = sn_remote_cmd(
            remote_ssh, "docker exec -it " + str(container_id_list[des - 1]) +
            " ifconfig | sed 's/[ \t].*//;/^\(eth0\|\)\(lo\|\)$/d'")
        des_IP = sn_remote_cmd(
            remote_ssh, "docker exec -it " + str(container_id_list[des - 1]) +
            " ifconfig " + ifconfig_output[0][:-1] +
            "|awk -F '[ :]+' 'NR==2{print $4}'")
    else:
        des_IP = sn_remote_cmd(
            remote_ssh, "docker exec -it " + str(container_id_list[des - 1]) +
            " ifconfig B" + str(des) +
            "-default |awk -F '[ :]+' 'NR==2{print $4}'")
    print('<>', src, des, des_IP)
    sn_remote_cmd(
        remote_ssh,
        "docker exec -id " + str(container_id_list[des - 1]) + " iperf3 -s ")
    print("iperf server success")
    perf_result = sn_remote_cmd(
        remote_ssh, "docker exec -i " + str(container_id_list[src - 1]) +
        " iperf3 -c " + str(des_IP[0][:-1]) + " -t 5 ")
    print("iperf client success")
    f = open(
        configuration_file_path + "/" + file_path + "/perf-" + str(src) + "-" +
        str(des) + "_" + str(time_index) + ".txt", "w")
    f.writelines(perf_result)
    f.close()
