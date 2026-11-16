#include "job_capture_control.h"
#include "job_capture_window.h"
#include "job_capture_snapshot.h"

#ifdef _WIN32
#include <windows.h>
#include <fcntl.h>
#include <io.h>
#include <cstdio>
#include <cstdlib>
#include <new>
#include <string>
#include <utility>

namespace {
struct control {
    std::wstring directory;
    job_capture_window window;
    job_capture* capture = nullptr;
#ifdef PORT_QUEUE_CALL_OBSERVATION
    job_queue_observer queue_observer{};
#endif
    control(std::wstring dir, const job_capture_config& config)
        : directory(std::move(dir)), window(config) {}
    std::wstring path(const wchar_t* name) const { return directory + L"\\" + name; }
};
uint64_t clock_qpc(void*) {
    LARGE_INTEGER v{};
    return QueryPerformanceCounter(&v) && v.QuadPart > 0 ? static_cast<uint64_t>(v.QuadPart) : 0;
}
uint64_t thread_id(void*) { return GetCurrentThreadId(); }
bool exists(const std::wstring& path) { return GetFileAttributesW(path.c_str()) != INVALID_FILE_ATTRIBUTES; }
DWORD WINAPI run_control(void* arg) {
    auto* c = static_cast<control*>(arg);
    const auto open_path = c->path(L"open"), snapshot_path = c->path(L"snapshot");
    while (!exists(open_path)) Sleep(25);
    uint64_t before = 0, after = 0;
    auto result = c->window.open(&before, &after);
    fprintf(stderr, "[job-capture] open result=%d before=%llu after=%llu\n",
            static_cast<int>(result), (unsigned long long)before, (unsigned long long)after);
    if (result == job_capture_window::rejected) return 1;
    while (!exists(snapshot_path)) Sleep(25);
    HANDLE file = CreateFileW(c->path(L"snapshot.bin").c_str(), GENERIC_WRITE, 0, nullptr,
                              CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) {
        fprintf(stderr, "[job-capture] snapshot create failed: %lu\n", GetLastError());
        return 1;
    }
    int fd = _open_osfhandle(reinterpret_cast<intptr_t>(file), _O_BINARY | _O_WRONLY);
    if (fd < 0) { CloseHandle(file); fprintf(stderr, "[job-capture] snapshot fd failed\n"); return 1; }
    FILE* stream = _fdopen(fd, "wb");
    if (!stream) { _close(fd); fprintf(stderr, "[job-capture] snapshot stream failed\n"); return 1; }
    int ok = job_capture_write_snapshot(c->capture, stream);
    if (fclose(stream)) ok = 0;
    fprintf(stderr, "[job-capture] snapshot %s (live partial view)\n", ok ? "written" : "failed");
    return ok ? 0 : 1;
}
}
int job_capture_control_start() {
    const DWORD size = GetEnvironmentVariableW(L"MS_JOB_CAPTURE_DIR", nullptr, 0);
    if (!size) return GetLastError() == ERROR_ENVVAR_NOT_FOUND ? 1 : 0;
    std::wstring dir(size, L'\0');
    DWORD got = GetEnvironmentVariableW(L"MS_JOB_CAPTURE_DIR", &dir[0], size);
    if (!got || got >= size) return 0;
    dir.resize(got);
    DWORD attributes = GetFileAttributesW(dir.c_str());
    if (attributes == INVALID_FILE_ATTRIBUTES || !(attributes & FILE_ATTRIBUTE_DIRECTORY)) return 0;
    LARGE_INTEGER frequency{}, start{};
    if (!QueryPerformanceFrequency(&frequency) || frequency.QuadPart <= 0 ||
        !QueryPerformanceCounter(&start) || start.QuadPart <= 0) return 0;
    uint64_t run_id = static_cast<uint64_t>(start.QuadPart) ^ (static_cast<uint64_t>(GetCurrentProcessId()) << 32);
    if (!run_id) return 0;
    job_capture_config config{run_id, static_cast<uint64_t>(frequency.QuadPart), 65536,
                              nullptr, clock_qpc, thread_id, nullptr, nullptr, nullptr, nullptr};
    auto* c = new (std::nothrow) control(std::move(dir), config);
    if (!c) return 0;
    if (!c->window.available() || exists(c->path(L"open")) || exists(c->path(L"snapshot")) ||
        exists(c->path(L"snapshot.bin"))) { delete c; return 0; }
    auto gated = c->window.config();
    c->capture = job_capture_start(&gated);
    if (!c->capture) { delete c; return 0; }
#ifdef PORT_QUEUE_CALL_OBSERVATION
    c->queue_observer = {c->capture, job_capture_queue_call};
    if (!job_queue_observer_install(&c->queue_observer)) {
        job_capture_stop(c->capture); delete c; return 0;
    }
#endif
    HANDLE thread = CreateThread(nullptr, 0, run_control, c, 0, nullptr);
    if (!thread) {
#ifdef PORT_QUEUE_CALL_OBSERVATION
        (void)job_queue_observer_install(nullptr);
#endif
        job_capture_stop(c->capture); delete c; return 0;
    }
    CloseHandle(thread);
    /* Deliberately process-lifetime: guest exit can bypass main and producers
     * are not joined here. The OS reclaims owner and thread on process exit. */
    fprintf(stderr, "[job-capture] armed run=%llu capacity=%u\n", (unsigned long long)run_id, config.capacity);
    return 1;
}
#else
#include <cstdlib>
int job_capture_control_start() { return std::getenv("MS_JOB_CAPTURE_DIR") == nullptr; }
#endif
