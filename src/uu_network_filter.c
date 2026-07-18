#define _GNU_SOURCE

#include <dlfcn.h>
#include <errno.h>
#include <ifaddrs.h>
#include <net/if.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

/*
 * Wine's nsiproxy builds the Windows adapter list from getifaddrs() and
 * if_nameindex().  UU 4.33 chooses the first non-loopback adapter instead of
 * the Linux default route.  On a multi-homed host that can bind UU to a slow
 * or asymmetric path.  This process-local preload exposes only one selected
 * interface plus loopback to the Wine service tree.
 *
 * The filter is deliberately fail-open.  With no UURB_NETWORK_INTERFACE, an
 * invalid value, an absent interface, or an allocation failure, callers see
 * the original host adapter list.
 */

typedef int (*getifaddrs_fn)(struct ifaddrs **);
typedef void (*freeifaddrs_fn)(struct ifaddrs *);
typedef struct if_nameindex *(*if_nameindex_fn)(void);
typedef void (*if_freenameindex_fn)(struct if_nameindex *);

static getifaddrs_fn real_getifaddrs;
static freeifaddrs_fn real_freeifaddrs;
static if_nameindex_fn real_if_nameindex;
static if_freenameindex_fn real_if_freenameindex;
static pthread_once_t symbols_once = PTHREAD_ONCE_INIT;
static pthread_mutex_t allocations_lock = PTHREAD_MUTEX_INITIALIZER;

struct ifaddrs_allocation {
    struct ifaddrs *visible;
    struct ifaddrs *original;
    struct ifaddrs_allocation *next;
};

struct nameindex_allocation {
    struct if_nameindex *visible;
    struct nameindex_allocation *next;
};

static struct ifaddrs_allocation *ifaddrs_allocations;
static struct nameindex_allocation *nameindex_allocations;

static void load_symbols(void)
{
    real_getifaddrs = (getifaddrs_fn)dlsym(RTLD_NEXT, "getifaddrs");
    real_freeifaddrs = (freeifaddrs_fn)dlsym(RTLD_NEXT, "freeifaddrs");
    real_if_nameindex = (if_nameindex_fn)dlsym(RTLD_NEXT, "if_nameindex");
    real_if_freenameindex =
        (if_freenameindex_fn)dlsym(RTLD_NEXT, "if_freenameindex");
}

static const char *selected_interface(void)
{
    const char *name = getenv("UURB_NETWORK_INTERFACE");

    if (!name || !*name || strcmp(name, "all") == 0)
        return NULL;
    if (strlen(name) >= IFNAMSIZ || strchr(name, '/') || strchr(name, ','))
        return NULL;
    return name;
}

static bool keep_interface(const char *name, const char *selected)
{
    return name &&
           (strcmp(name, selected) == 0 || strcmp(name, "lo") == 0);
}

int getifaddrs(struct ifaddrs **result)
{
    const char *selected;
    struct ifaddrs *original;
    struct ifaddrs *first = NULL;
    struct ifaddrs *last = NULL;
    struct ifaddrs *entry;
    struct ifaddrs_allocation *record;
    bool selected_found = false;
    int status;

    pthread_once(&symbols_once, load_symbols);
    if (!result) {
        errno = EINVAL;
        return -1;
    }
    if (!real_getifaddrs || !real_freeifaddrs) {
        errno = ENOSYS;
        return -1;
    }

    status = real_getifaddrs(&original);
    if (status != 0)
        return status;
    *result = original;

    selected = selected_interface();
    if (!selected)
        return status;

    for (entry = original; entry; entry = entry->ifa_next) {
        if (entry->ifa_name && strcmp(entry->ifa_name, selected) == 0) {
            selected_found = true;
            break;
        }
    }
    if (!selected_found)
        return status;

    record = calloc(1, sizeof(*record));
    if (!record)
        return status;

    for (entry = original; entry; entry = entry->ifa_next) {
        struct ifaddrs *copy;

        if (!keep_interface(entry->ifa_name, selected))
            continue;
        copy = malloc(sizeof(*copy));
        if (!copy) {
            while (first) {
                struct ifaddrs *next = first->ifa_next;

                free(first);
                first = next;
            }
            free(record);
            return status;
        }
        *copy = *entry;
        copy->ifa_next = NULL;
        if (!first)
            first = copy;
        if (last)
            last->ifa_next = copy;
        last = copy;
    }
    if (!first) {
        free(record);
        return status;
    }
    last->ifa_next = NULL;

    record->visible = first;
    record->original = original;
    pthread_mutex_lock(&allocations_lock);
    record->next = ifaddrs_allocations;
    ifaddrs_allocations = record;
    pthread_mutex_unlock(&allocations_lock);
    *result = first;
    return status;
}

void freeifaddrs(struct ifaddrs *visible)
{
    struct ifaddrs_allocation **link;
    struct ifaddrs_allocation *record = NULL;

    pthread_once(&symbols_once, load_symbols);
    if (!real_freeifaddrs)
        return;

    pthread_mutex_lock(&allocations_lock);
    for (link = &ifaddrs_allocations; *link; link = &(*link)->next) {
        if ((*link)->visible == visible) {
            record = *link;
            *link = record->next;
            break;
        }
    }
    pthread_mutex_unlock(&allocations_lock);

    if (record) {
        while (visible) {
            struct ifaddrs *next = visible->ifa_next;

            free(visible);
            visible = next;
        }
        real_freeifaddrs(record->original);
        free(record);
    } else {
        real_freeifaddrs(visible);
    }
}

struct if_nameindex *if_nameindex(void)
{
    const char *selected;
    struct if_nameindex *original;
    struct if_nameindex *visible;
    struct nameindex_allocation *record;
    size_t count = 0;
    size_t position = 0;
    bool selected_found = false;

    pthread_once(&symbols_once, load_symbols);
    if (!real_if_nameindex || !real_if_freenameindex)
        return NULL;

    original = real_if_nameindex();
    selected = selected_interface();
    if (!original || !selected)
        return original;

    for (struct if_nameindex *entry = original; entry->if_index; ++entry) {
        if (entry->if_name && strcmp(entry->if_name, selected) == 0)
            selected_found = true;
        if (keep_interface(entry->if_name, selected))
            ++count;
    }
    if (!selected_found || !count)
        return original;

    visible = calloc(count + 1, sizeof(*visible));
    record = calloc(1, sizeof(*record));
    if (!visible || !record) {
        free(visible);
        free(record);
        return original;
    }

    for (struct if_nameindex *entry = original; entry->if_index; ++entry) {
        if (!keep_interface(entry->if_name, selected))
            continue;
        visible[position].if_index = entry->if_index;
        visible[position].if_name = strdup(entry->if_name);
        if (!visible[position].if_name) {
            for (size_t index = 0; index < position; ++index)
                free(visible[index].if_name);
            free(visible);
            free(record);
            return original;
        }
        ++position;
    }
    real_if_freenameindex(original);

    record->visible = visible;
    pthread_mutex_lock(&allocations_lock);
    record->next = nameindex_allocations;
    nameindex_allocations = record;
    pthread_mutex_unlock(&allocations_lock);
    return visible;
}

void if_freenameindex(struct if_nameindex *visible)
{
    struct nameindex_allocation **link;
    struct nameindex_allocation *record = NULL;

    pthread_once(&symbols_once, load_symbols);
    if (!real_if_freenameindex)
        return;

    pthread_mutex_lock(&allocations_lock);
    for (link = &nameindex_allocations; *link; link = &(*link)->next) {
        if ((*link)->visible == visible) {
            record = *link;
            *link = record->next;
            break;
        }
    }
    pthread_mutex_unlock(&allocations_lock);

    if (!record) {
        real_if_freenameindex(visible);
        return;
    }
    for (struct if_nameindex *entry = visible; entry->if_index; ++entry)
        free(entry->if_name);
    free(visible);
    free(record);
}
