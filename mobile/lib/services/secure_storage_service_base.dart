/// Pure-Dart interface for token + server-URL storage.
///
/// Production code uses [SecureStorageService] (backed by
/// `flutter_secure_storage`). Tests can implement this directly to avoid
/// pulling the native plugin into the test binary's link graph, which on
/// Linux CI causes `flutter_tester` to SIGSEGV during `--coverage`
/// finalization.
abstract class SecureStorageServiceBase {
  Future<String?> getAccessToken();
  Future<String?> getRefreshToken();
  Future<void> saveTokens({required String access, required String refresh});
  Future<void> clearTokens();
  Future<void> saveServerUrl(String url);
  Future<String?> getServerUrl();
}
