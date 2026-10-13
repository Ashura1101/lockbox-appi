import 'dart:async';
import 'dart:io';
import 'package:http/http.dart' as http;
import '../services/api_service.dart';

String mensajeDeError(Object e, {String accion = 'completar la operación'}) {
  if (e is ApiException) return e.message;
  if (e is SocketException || e is http.ClientException) {
    return 'Sin conexión a internet: no se pudo $accion. Inténtalo de nuevo cuando tengas conexión.';
  }
  if (e is TimeoutException) {
    return 'El servidor tardó demasiado en responder al intentar $accion. Inténtalo de nuevo.';
  }
  if (e is FormatException) {
    return 'El servidor respondió de forma inesperada al intentar $accion. Inténtalo de nuevo en unos segundos.';
  }
  return 'Ocurrió un error inesperado al intentar $accion. Inténtalo de nuevo.';
}