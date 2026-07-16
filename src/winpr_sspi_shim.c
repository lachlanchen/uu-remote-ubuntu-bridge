#define WIN32_LEAN_AND_MEAN
#define SECURITY_WIN32 1
#define _NO_KSECDD_IMPORT_ 1
#include <windows.h>
#include <sspi.h>
#include <string.h>

#define SSPI_INTERFACE_WINPR 0x00000001u

typedef void *(WINAPI *init_security_interface_ex_fn)(DWORD flags);

static SecurityFunctionTableA patched_a;
static SecurityFunctionTableW patched_w;
static SecurityFunctionTableA *original_a;
static SecurityFunctionTableW *original_w;
static const char negotiate_name[] = "Negotiate";

static void fix_handle_name(PSecHandle handle)
{
    if (handle != NULL && handle->dwLower != 0) {
        /* WinPR stores handle pointers with every bit inverted. */
        handle->dwUpper = ~((ULONG_PTR)negotiate_name);
    }
}

static SECURITY_STATUS WINAPI patched_acquire_credentials_a(
    SEC_CHAR *principal, SEC_CHAR *package, ULONG credential_use,
    void *logon_id, void *auth_data, SEC_GET_KEY_FN get_key,
    void *get_key_argument, PCredHandle credential, PTimeStamp expiry)
{
    SECURITY_STATUS status = original_a->AcquireCredentialsHandleA(
        principal, package, credential_use, logon_id, auth_data, get_key,
        get_key_argument, credential, expiry);

    if (status == SEC_E_OK)
        fix_handle_name(credential);
    return status;
}

static SECURITY_STATUS WINAPI patched_acquire_credentials_w(
    SEC_WCHAR *principal, SEC_WCHAR *package, ULONG credential_use,
    void *logon_id, void *auth_data, SEC_GET_KEY_FN get_key,
    void *get_key_argument, PCredHandle credential, PTimeStamp expiry)
{
    SECURITY_STATUS status = original_w->AcquireCredentialsHandleW(
        principal, package, credential_use, logon_id, auth_data, get_key,
        get_key_argument, credential, expiry);

    if (status == SEC_E_OK)
        fix_handle_name(credential);
    return status;
}

static SECURITY_STATUS WINAPI patched_initialize_context_a(
    PCredHandle credential, PCtxtHandle context, SEC_CHAR *target,
    ULONG context_requirements, ULONG reserved1, ULONG data_representation,
    PSecBufferDesc input, ULONG reserved2, PCtxtHandle new_context,
    PSecBufferDesc output, ULONG *context_attributes, PTimeStamp expiry)
{
    fix_handle_name(credential);
    fix_handle_name(context);

    SECURITY_STATUS status = original_a->InitializeSecurityContextA(
        credential, context, target, context_requirements, reserved1,
        data_representation, input, reserved2, new_context, output,
        context_attributes, expiry);

    fix_handle_name(new_context);
    return status;
}

static SECURITY_STATUS WINAPI patched_initialize_context_w(
    PCredHandle credential, PCtxtHandle context, SEC_WCHAR *target,
    ULONG context_requirements, ULONG reserved1, ULONG data_representation,
    PSecBufferDesc input, ULONG reserved2, PCtxtHandle new_context,
    PSecBufferDesc output, ULONG *context_attributes, PTimeStamp expiry)
{
    fix_handle_name(credential);
    fix_handle_name(context);

    SECURITY_STATUS status = original_w->InitializeSecurityContextW(
        credential, context, target, context_requirements, reserved1,
        data_representation, input, reserved2, new_context, output,
        context_attributes, expiry);

    fix_handle_name(new_context);
    return status;
}

static void *init_winpr_interface(const char *symbol)
{
    HMODULE module = GetModuleHandleA("libwinpr3.dll");
    if (module == NULL)
        module = LoadLibraryA("libwinpr3.dll");
    if (module == NULL)
        return NULL;

    FARPROC address = GetProcAddress(module, symbol);
    init_security_interface_ex_fn init = NULL;
    if (address == NULL)
        return NULL;
    memcpy(&init, &address, sizeof(init));
    return init(SSPI_INTERFACE_WINPR);
}

__declspec(dllexport) PSecurityFunctionTableA WINAPI InitSecurityInterfaceA(void)
{
    if (original_a == NULL) {
        original_a = (SecurityFunctionTableA *)
            init_winpr_interface("InitSecurityInterfaceExA");
        if (original_a == NULL)
            return NULL;

        patched_a = *original_a;
        patched_a.AcquireCredentialsHandleA = patched_acquire_credentials_a;
        patched_a.InitializeSecurityContextA = patched_initialize_context_a;
    }

    return &patched_a;
}

__declspec(dllexport) PSecurityFunctionTableW WINAPI InitSecurityInterfaceW(void)
{
    if (original_w == NULL) {
        original_w = (SecurityFunctionTableW *)
            init_winpr_interface("InitSecurityInterfaceExW");
        if (original_w == NULL)
            return NULL;

        patched_w = *original_w;
        patched_w.AcquireCredentialsHandleW = patched_acquire_credentials_w;
        patched_w.InitializeSecurityContextW = patched_initialize_context_w;
    }

    return &patched_w;
}
