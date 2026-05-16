abstract class NotificationServiceBase {
  Future<void> registerWithServer();
  Future<void> deregister();
}
