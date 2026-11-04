/// Riverpod retry policy for the app's [ProviderScope].
///
/// Riverpod 3 retries failed providers automatically (with exponential
/// backoff) by default. The app was written for Riverpod 2, where a failure
/// stays a failure until the user pulls to refresh, so keep that behaviour.
Duration? noProviderRetry(int retryCount, Object error) => null;
