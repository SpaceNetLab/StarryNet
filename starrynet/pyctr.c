#include <Python.h>

#ifndef _GNU_SOURCE
# define _GNU_SOURCE
#endif

#include <unistd.h>
#include <sched.h>
#include <syscall.h>
#include <fcntl.h>
#include <sys/mount.h>
#include <sys/wait.h>
#include <sys/eventfd.h>

#include <signal.h>
#include <errno.h>
#include <string.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>

const int NS = CLONE_NEWNS|CLONE_NEWPID|CLONE_NEWNET|CLONE_NEWIPC|CLONE_NEWUTS;

static int child_err(const char *prefix, int write_fd) {
    int err = errno;
    const char *error_msg = strerror(err);
    write(write_fd, prefix, strlen(prefix));
    write(write_fd, error_msg, strlen(error_msg));
    close(write_fd);
    return err;
}

// in child process with new namespace
static int container_init(
    const char* newroot,
    const char* overlay_opt,
    const char* hostname,
    int err_fd
    ) {
    close(STDIN_FILENO);
    close(STDOUT_FILENO);
    close(STDERR_FILENO);
    int flags = fcntl(err_fd, F_GETFD);
    flags |= FD_CLOEXEC;
    fcntl(err_fd, F_SETFD, flags);

    if(mount("none", "/", NULL, MS_PRIVATE|MS_REC, NULL) != 0) {
        return child_err("mount rprivate / failed: ", err_fd);
    }
    // mount overlay
    if(mount("overlay", newroot, "overlay", 0, overlay_opt) != 0) {
        return child_err("mount overlay failed: ", err_fd);
    }
    if(mount("none", newroot, NULL, MS_PRIVATE|MS_REC, NULL) != 0) {
        return child_err("mount rprivate newroot failed: ", err_fd);
    }

    if(chdir(newroot) != 0) {
        return child_err("chdir failed: ", err_fd);
    }
    // pivot root
    // https://unix.stackexchange.com/questions/456620/how-to-perform-chroot-with-linux-namespaces
    if(syscall(SYS_pivot_root, ".", ".") != 0) {
        return child_err("pivot_root failed: ", err_fd);
    }
    if(chroot(".") != 0) {
        return child_err("chroot failed: ", err_fd);
    }
    if(umount2 (".", MNT_DETACH) != 0) {
        return child_err("umount2 failed: ", err_fd);
    }
    // mount proc
    if(mount("proc", "/proc", "proc", MS_NOSUID|MS_NOEXEC|MS_NODEV, NULL) != 0) {
        return child_err("mount /proc failed: ", err_fd);
    }
    // new session, detach to become a daemon process 
    if(setsid() < 0) {
        return child_err("setsid failed: ", err_fd);
    }

    // other miscellaneous configuration, maybe warning is better choice
    if(signal(SIGCLD, SIG_IGN) < 0) {
        return child_err("ignore SIGCLD failed: ", err_fd);
    }
    if(sethostname(hostname, strlen(hostname))) {
        return child_err("sethostname failed: ", err_fd);
    }
    if(clearenv() != 0) {
        return child_err("clearenv failed: ", err_fd);
    }
    if(putenv("HOME=/root")
    || putenv("PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")) {
        return child_err("putenv failed: ", err_fd);
    }
    // sleep infinity, need a process with low resource requirement
    execlp("sleep", "sleep", "inf", NULL);
    // should not be executed here
    return child_err("execlp failed: ", err_fd);
}

// in child process
int container_enter(pid_t ctr_pid, char *const* argv, int err_fd) {
    int flags = fcntl(err_fd, F_GETFD);
    if(flags < 0)
        return child_err("failed to fcntl F_GETFD: ", err_fd);
    flags |= FD_CLOEXEC;
    if(fcntl(err_fd, F_SETFD, flags) < 0)
        return child_err("failed to fcntl F_SETFD: ", err_fd);

    int pid_fd = syscall(SYS_pidfd_open, ctr_pid, 0);
    if(pid_fd < 0)
        return child_err("failed to pidfd_open: ", err_fd);

    int ret = setns(pid_fd, NS);
    close(pid_fd);
    if(ret != 0)
        return child_err("failed to setns: ", err_fd);

    execvp(argv[0], &argv[0]);
    return child_err("failed to execvp: ", err_fd);
}

// in parent process
// on success, ret > 0 means child pid.
// ret < 0 for parent err, ret == 0 for child err
static int container_run_inner(
    const char *base_dir, const char *hostname, char *chd_err, size_t max_len) {
    // 0755
    const mode_t MODE = S_IRWXU | (S_IRGRP|S_IXGRP) | (S_IROTH|S_IXOTH);
    const char* UPPER_DIR = "upper";
    const char* WORK_DIR = "work";
    const char* NEWROOT = "rootfs";

    if(access(base_dir, F_OK) && mkdir(base_dir, MODE)) return -1;

    int dir_fd = open(base_dir, O_RDONLY);
    if(dir_fd < 0) return -1;
    if((faccessat(dir_fd, UPPER_DIR, F_OK, 0) && mkdirat(dir_fd, UPPER_DIR, MODE))
    || (faccessat(dir_fd, WORK_DIR, F_OK, 0) && mkdirat(dir_fd, WORK_DIR, MODE))
    || (faccessat(dir_fd, NEWROOT, F_OK, 0) && mkdirat(dir_fd, NEWROOT, MODE))) {
        close(dir_fd);
        return -1;
    }
    if(close(dir_fd) != 0) return -1;

    char overlay_opt[PATH_MAX * 3];
    char new_root[PATH_MAX];
    snprintf(overlay_opt, sizeof(overlay_opt),
        "lowerdir=/,upperdir=%s/%s,workdir=%s/%s",
        base_dir, UPPER_DIR, base_dir, WORK_DIR);
    snprintf(new_root, sizeof(new_root), "%s/%s", base_dir, NEWROOT);
    
    int err_fds[2], event_fd;
    if(pipe(err_fds) != 0 || (event_fd = eventfd(0, 0)) < 0) return -1;
    
    pid_t pid = fork();
    if(pid < 0) {
        close(err_fds[0]), close(err_fds[1]), close(event_fd);
        return -1;  
    } else if(pid == 0) {
        close(err_fds[0]);
        if(unshare(NS) != 0) {
            close(event_fd);
            exit(child_err("unshare failed: ", err_fds[1]));
        }
        pid = fork();
        if(pid < 0) {
            close(event_fd);
            exit(child_err("second fork failed: ", err_fds[1]));
        } else if(pid == 0) {
            close(event_fd);
            exit(container_init(new_root, overlay_opt, hostname, err_fds[1]));
            // should not execute here
        }
        close(err_fds[1]);
        uint64_t pid_u64 = pid;
        write(event_fd, &pid_u64, sizeof(pid_u64));
        close(event_fd);
        exit(0);
        // should not execute here
    }
    
    close(err_fds[1]);
    ssize_t len = read(err_fds[0], chd_err, max_len);
    // anyway, child should exit immediately 
    waitpid(pid, NULL, 0);
    if(len > 0) {
        chd_err[len] = '\0';
        close(err_fds[0]), close(event_fd);
        return 0;
    }

    // receive grandchild pid from child
    uint64_t pid_u64;
    if(read(event_fd, &pid_u64, sizeof(pid_u64)) == sizeof(pid_u64))
        pid = pid_u64;
    else
        pid = -1;

    close(err_fds[0]), close(event_fd);
    return pid;
}

// in parent process
// on success, ret > 0 means child pid, need to be waited and recycled
// ret < 0 for parent err, ret == 0 for child err
static int container_exec_inner(
    pid_t ctr_pid, char *const* argv, char *chd_err, size_t max_len) {
    int err_fds[2];
    pid_t ret;
    ssize_t err_len;

    if(pipe(err_fds) != 0) return -1;

    ret = fork();
    if(ret < 0) {
        close(err_fds[0]), close(err_fds[1]);
        return -1;
    } else if(ret == 0) {
        close(err_fds[0]);
        exit(container_enter(ctr_pid, argv, err_fds[1]));
        // should not be executed
    }
    close(err_fds[1]);

    err_len = read(err_fds[0], chd_err, max_len);
    if(err_len > 0) {
        chd_err[err_len] = '\0';
        waitpid(ret, NULL, 0);
        ret = 0;
    }
    close(err_fds[0]);
    return ret;
}

// ========================Python wrapper========================

static PyObject *container_run(PyObject *self, PyObject *args) {
    const char *base_dir = NULL;
    const char *hostname = NULL;
    char chd_err[256];
    int pid;

    if (!PyArg_ParseTuple(args,
        "ss:container_run(base_dir, hostname)", &base_dir, &hostname))
        return NULL;

    pid = container_run_inner(base_dir, hostname, chd_err, sizeof(chd_err) - 1);
    if(pid < 0) {
        PyErr_SetFromErrno(PyExc_OSError);
        return NULL;
    } else if (pid == 0) {
        PyErr_SetString(PyExc_ChildProcessError, chd_err);
        return NULL;
    } else { // normal case
        return PyLong_FromLong(pid);
    }
}

static PyObject *container_exec(PyObject *self, PyObject *args) {
    int pid;
    PyObject *cmdline;
    Py_ssize_t argc;
    char **argv;
    char chd_err[256];
    int ret;

    if(!PyArg_ParseTuple(args,
        "iO:container_exec(container_pid, cmdline)", &pid, &cmdline))
        return NULL;
    if(!PySequence_Check(cmdline) || (argc = PySequence_Size(cmdline)) <= 0) {
        PyErr_SetString(PyExc_TypeError, 
            "argument 2 \"cmdline\" must be sequence with length >= 1");
        return NULL;
    }

    argv = malloc((argc + 1) * sizeof(*argv));
    for(Py_ssize_t i = 0; i < argc; i++) {
        argv[i] = PyBytes_AsString(PySequence_ITEM(cmdline, i));
        if(argv[i] == NULL) {
            free(argv);
            return NULL;
        }
    }
    argv[argc] = NULL;

    ret = container_exec_inner(pid, argv, chd_err, sizeof(chd_err) - 1);
    if(ret < 0) {
        PyErr_SetFromErrno(PyExc_OSError);
    } else if (ret == 0) {
        PyErr_SetString(PyExc_ChildProcessError, chd_err);
    } else {
        int status;
        waitpid(ret, &status, 0);
        if(!WIFEXITED(status)) {
            PyErr_SetString(PyExc_ChildProcessError, "child did not exit normally");
        } else {
            free(argv);
            return PyLong_FromLong(WEXITSTATUS(status));
        }
    }
    free(argv);
    return NULL;
}

static PyMethodDef methods[] = {
    {"container_run",  container_run, METH_VARARGS, "run a simplified container"},
    {"container_exec", container_exec, METH_VARARGS, "exec command in container"},
    {NULL, NULL, 0, NULL}        /* Sentinel */
};

static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT,
    "pyctr",   /* name of module */
    NULL, /* module documentation, may be NULL */
    -1,       /* size of per-interpreter state of the module,
                 or -1 if the module keeps state in global variables. */
    methods
};

PyMODINIT_FUNC PyInit_pyctr(void) {
    return PyModule_Create(&module);
}
