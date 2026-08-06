#pragma once

#include <cstddef>
#include <cstdint>

#include "psa/crypto.h"

// ESP-IDF 6.0.2 ships Mbed TLS 4, which no longer exposes the legacy
// mbedtls/sha256.h streaming API used by the first OTA implementation.
// Keep this adapter private to service_ota and implement the same small API
// on top of the supported PSA Crypto hash interface.

typedef struct mbedtls_sha256_context {
    psa_hash_operation_t operation;
    bool active;
} mbedtls_sha256_context;

static inline void mbedtls_sha256_init(mbedtls_sha256_context* context)
{
    if (context == nullptr) {
        return;
    }
    const psa_hash_operation_t initial = PSA_HASH_OPERATION_INIT;
    context->operation = initial;
    context->active = false;
}

static inline int mbedtls_sha256_starts(mbedtls_sha256_context* context,
                                        const int is224)
{
    if (context == nullptr || is224 != 0) {
        return -1;
    }
    if (psa_crypto_init() != PSA_SUCCESS) {
        return -1;
    }
    const psa_status_t status = psa_hash_setup(
        &context->operation,
        PSA_ALG_SHA_256);
    context->active = status == PSA_SUCCESS;
    return context->active ? 0 : -1;
}

static inline int mbedtls_sha256_update(mbedtls_sha256_context* context,
                                        const unsigned char* input,
                                        const std::size_t input_length)
{
    if (context == nullptr || !context->active ||
        (input == nullptr && input_length != 0)) {
        return -1;
    }
    return psa_hash_update(&context->operation, input, input_length) == PSA_SUCCESS
               ? 0
               : -1;
}

static inline int mbedtls_sha256_finish(mbedtls_sha256_context* context,
                                        unsigned char output[32])
{
    if (context == nullptr || !context->active || output == nullptr) {
        return -1;
    }
    std::size_t output_length = 0;
    const psa_status_t status = psa_hash_finish(
        &context->operation,
        output,
        32,
        &output_length);
    context->active = false;
    return status == PSA_SUCCESS && output_length == 32 ? 0 : -1;
}

static inline void mbedtls_sha256_free(mbedtls_sha256_context* context)
{
    if (context == nullptr) {
        return;
    }
    if (context->active) {
        static_cast<void>(psa_hash_abort(&context->operation));
    }
    const psa_hash_operation_t initial = PSA_HASH_OPERATION_INIT;
    context->operation = initial;
    context->active = false;
}
