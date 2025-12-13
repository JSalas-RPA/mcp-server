// --- CONFIGURACIÓN PRINCIPAL ---

// ⚠️ 1. CAMBIA ESTO: Nombre real de tu Bucket de GCS (ej: rpa-facturacion)
const BUCKET_NAME = "rpa_facturacion"; 
const CARPETA_DESTINO = "entrada_facturas/";

// ⚠️ 2. PEGA AQUÍ EL CONTENIDO COMPLETO DE TU ARCHIVO JSON DE LA SERVICE ACCOUNT
// Asegúrate de que todo esté en una sola línea o usar plantillas de cadena (`...`)
const SERVICE_ACCOUNT_KEY_JSON_STRING = `
{
  "type": "service_account",
  "project_id": "datec-d4g-adn",
  "private_key": "-----BEGIN PRIVATE KEY-----\\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC/yYm4L8lFY5ff\\nwCm8wiEDtC7vV5Ob/NHFsqXmKkz1MzS90BC/F034N1jkMonH+gKxMMJE3XLLML/2\\nT2dTliUsoygIUK6IwHtT8gM5qnX8ROAamThJxZGcyU/Av81y7cL7haXXklz1ynXD\\nYjCorvp0+GNW2gU0Z8XU+bzE/ZIRQsN+ifqN4CrITTuk39iFeC8nIO5lOA9bD4Yy\\nSDPhdfwhU5i0RSqcjY8MLFu3/Ik0Mb81t0+QNgv4UuVyAEBK4HQGlsbTTW4Jq7nC\\nJtiEeoXbeIagWEyfyGdIiJafDb/9+UCwHQLstvMBnG/bdDnwicmO5TDarkM9qAdT\\nNydBowvlAgMBAAECggEAH92TlVfTQEU48cNS6/rxU1U3yyqo6u0JyahSKjjzCnaU\\nl8kfTzDHEqvXiCrhe6mNkvVAAgMtVJdn/bvZtiinSpBdUWxeY3hfxWXbpVQuQFkN\\nRz4X/SHnfL5yEtuLfkIE+JePI489BNW71VfWL+DK2m5+yup0nO11EFriQ3TCNT2x\\n5m6vik7pnhRQQUo0jKvETBRBPJwNI1W0F59kpFHITiJG/C7i12pmoj5tU1NlDu8Z\\nsTzg9Kn9w2FcBpajJczzK6+sjawtJW5sOFEZjVviuxdHoK8wkrynS7kYqeuG7chz\\nxznnxGNJdT1vSSuR32q/8BMGa9/Fgh07md2Ex9YlQQKBgQDj4KhLVKmAtCJNsplM\\n4N5S4PnznVukGQIPAExN/sQ2n8G0qzaTXEOhQKqhaPhulIWjfYXB5aUa3op/be3y\\nU53gdzKNzB8+uCpFZ0qYXljdE4xPCZfoOVRK1oNu/odgR3J0NndmxzxkrrRNBGAM\\n6KN6HzUrUTq1gXEzJwAeM9D4FQKBgQDXdK2oVdCD7Bu78zSEYZ0bBpeDrrLV9e5a\\nFQ4otSVI58EGg3/6ktme4V6dL4Tt+Hc4OqkS0F8XM54MKXvY1DRUfc9IEPeHR0P1\\n7KlgyyM7e9IarCZfUuNP/m+ZTB6gwf2O0OxgBkedDV3onYGdIG3uUhzoeyEYYEva\\neJiWJwZokQKBgBcLzXlw4oOltCJvgZmI1HNFVYIR1AbQkKi7uvvYXDe6CHkhJ6/X\\nkO9p/te8KgPk+W8DbtehRgVlpFQm5f2v/zOIWpCEqFRLg9rpC15FjG8vXu1PZxGR\\nWrkG4NwE2eQe1bBzIbg/RhhYott3Kc+kZ4QeS95JpMpegPhPZW+oheXRAoGBALdd\\nte3uGugrqe7rrWZ9LRgzJAAOTmWKSLCh+srqYDEMDFtezyySjmOJqtxb9OYS8GQK\\niJpafJNiesAfDigbce32pNLQndmj7VL/d6fJOtMFLmtE1+OIx6zs/k2ZWve2IfXK\\nGWIf9hLTrXirlAQF9Yk+mRvCrwfv7J6ixDoGPI4BAoGBALTd92Mx7rsac6EHnOQ6\\nctpm/j/cMmnaxjWRFaH3pHEpARYTEJQs/GvIT92gdZ+NXEdDeud6nfraUYoicdrz\\nOXDtRXA1Jy500WV+Lfn3n93+Nlv8uszLSqayAI4FlF4R+yPn15bF8AbMextXA2ef\\n6UzaZ7JkSEXsyQTh8pKt2Jt2\\n-----END PRIVATE KEY-----\\n",
  "client_email": "mcp-server-dsuite@datec-d4g-adn.iam.gserviceaccount.com",
  "client_id": "111173590275359323720",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/mcp-server-dsuite%40datec-d4g-adn.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}

`;

const SA_KEY = JSON.parse(SERVICE_ACCOUNT_KEY_JSON_STRING);

// ⚠️ 3. URL de tu servidor Flask (Agent)
const AGENT_WEBHOOK_URL = "https://agent-dsuite-facturacion-885151715761.us-central1.run.app/webhook-facturas";
const AUTH_SECRET = "MiClaveUltraSecreta_MCP_2025_#f6d9kP!";

// --- LÓGICA DE AUTENTICACIÓN (JWT MANUAL) ---

/**
 * Genera el JWT y solicita un Access Token a Google.
 */
function getGCSAccessToken() {
  
  const token_uri = SA_KEY.token_uri;
  const privateKey = SA_KEY.private_key;
  const clientEmail = SA_KEY.client_email;
  const scopes = "https://www.googleapis.com/auth/devstorage.read_write"; // Alcance para GCS

  // 1. Crear el Encabezado (Header)
  const header = {
    alg: "RS256",
    typ: "JWT"
  };
  const headerBase64 = Utilities.base64Encode(JSON.stringify(header)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

  // 2. Crear la Carga Útil (Claim Set)
  const now = Math.floor(Date.now() / 1000);
  const claimSet = {
    iss: clientEmail,
    scope: scopes,
    aud: token_uri,
    exp: now + 3600, // Token válido por 1 hora
    iat: now
  };
  const claimSetBase64 = Utilities.base64Encode(JSON.stringify(claimSet)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  
  // 3. Crear el JWT sin firmar
  const unsignedJwt = headerBase64 + "." + claimSetBase64;

  // 4. Firmar el JWT
  const signature = Utilities.computeRsaSha256Signature(
      unsignedJwt, 
      privateKey
  );
  const signatureBase64 = Utilities.base64Encode(signature).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

  // 5. JWT Completo
  const signedJwt = unsignedJwt + "." + signatureBase64;
  
  // 6. Solicitar el Access Token a Google
  const response = UrlFetchApp.fetch(token_uri, {
    method: 'POST',
    contentType: 'application/x-www-form-urlencoded',
    payload: `grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer&assertion=${signedJwt}`,
    muteHttpExceptions: true // Necesario para leer errores de Google
  });
  
  const responseData = JSON.parse(response.getContentText());
  
  if (responseData.access_token) {
    Logger.log("✅ Token de Acceso GCS obtenido con éxito.");
    return responseData.access_token;
  } else {
    Logger.log(`❌ Fallo en obtener token: ${responseData.error_description || response.getContentText()}`);
    throw new Error("Fallo en la autenticación con Service Account.");
  }
}

function procesarCorreosYSubirAGCS() {
    try {
        const accessToken = getGCSAccessToken();
        const query = 'has:attachment is:unread (subject:factura OR subject:Factura OR subject:facturación OR subject:Facturación OR subject:facturacion OR subject:Facturacion OR subject:invoice OR subject:Invoice)';
        const threads = GmailApp.search(query, 0, 10); // Procesamos un máximo de 10 hilos

        if (threads.length === 0) {
            Logger.log("📭 No hay correos nuevos para procesar.");
            return;
        }

        Logger.log(`📬 Encontrados ${threads.length} hilos. Subiendo a GCS.`);

        // Tipos MIME permitidos
        const allowedMimeTypes = [
            "application/pdf", "application/vnd.openxmlformats-officedocument", // docx, xlsx, etc.
            "application/msword", "application/vnd.ms-excel",
            "text/plain"
        ];

        for (const thread of threads) {
            const messages = thread.getMessages();
            for (const message of messages) {
                if (message.isUnread()) {
                    const attachments = message.getAttachments();
                    const sender = message.getFrom();
                    const subject = message.getSubject();
                    const safeSender = sender.replace(/[^a-zA-Z0-9@._-]/g, "_");
                    let procesado = false;
                    let gcsPathFinal = null; // ⚠️ Guardar la ruta final

                    for (const attachment of attachments) {
                        const contentType = attachment.getContentType();
                        const fileName = attachment.getName();

                        // Verificamos si es un tipo permitido
                        if (allowedMimeTypes.some(type => contentType.includes(type))) {

                            const objectName = `${CARPETA_DESTINO}${safeSender}/${new Date().getTime()}_${fileName}`;

                            try {
                                const blob = attachment.copyBlob();

                                const uploadUrl = `https://storage.googleapis.com/upload/storage/v1/b/${BUCKET_NAME}/o?uploadType=media&name=${encodeURIComponent(objectName)}`;

                                // Subida a GCS usando el Access Token
                                const response = UrlFetchApp.fetch(uploadUrl, {
                                    method: "POST",
                                    contentType: blob.getContentType(),
                                    payload: blob.getBytes(),
                                    headers: {
                                        Authorization: 'Bearer ' + accessToken
                                    },
                                    muteHttpExceptions: true
                                });

                                if (response.getResponseCode() === 200) {
                                    gcsPathFinal = `gs://${BUCKET_NAME}/${objectName}`;
                                    Logger.log(`   ✅ Subido exitosamente a: ${gcsPathFinal}`);
                                    procesado = true;
                                    
                                    // --- ENVIAR WEBHOOK INMEDIATAMENTE ---
                                    enviarWebhookAlAgente(gcsPathFinal, sender, subject, thread.getId());
                                    break; // Salir del bucle después de enviar webhook
                                } else {
                                    Logger.log(`   ❌ Fallo GCS: HTTP ${response.getResponseCode()} - ${response.getContentText()}`);
                                }

                            } catch (e) {
                                Logger.log(`   ❌ Error en subida: ${e.toString()}`);
                            }
                        }
                    } // Fin del bucle de attachments

                    // Marcar como leído si se procesó
                    if (procesado) {
                        message.markRead();
                        Logger.log("   📩 Correo marcado como leído.");
                    }
                }
            }
        }
    } catch (e) {
        Logger.log(`💥 Error crítico en la ejecución: ${e.toString()}`);
    }
}



/**
 * Extrae solo la dirección de correo de una cadena "Nombre <email>"
 */
function extractEmail(fullAddress) {
  const match = fullAddress.match(/<([^>]+)>/);
  return match ? match[1] : fullAddress;
}

/**
 * Envía notificación al agente Flask
 */
function enviarWebhookAlAgente(gcsPath, remitente, asunto, threadId) {
  try {
    const payload = {
      gcs_path: gcsPath,
      remitente_correo: remitente,
      asunto_correo: asunto,
      thread_id: threadId,
      timestamp: new Date().toISOString(),
      auth_secret: AUTH_SECRET
    };
    
    Logger.log(`📡 Enviando webhook al agente: ${AGENT_WEBHOOK_URL}`);
    Logger.log(`   Payload: ${JSON.stringify(payload)}`);
    
    const options = {
      method: "POST",
      contentType: "application/json",
      payload: JSON.stringify(payload),
      muteHttpExceptions: true,
      timeout: 30000 // 30 segundos timeout
    };
    
    const response = UrlFetchApp.fetch(AGENT_WEBHOOK_URL, options);
    const responseCode = response.getResponseCode();
    const responseText = response.getContentText();
    
    Logger.log(`   ✅ Webhook enviado. Respuesta: HTTP ${responseCode}`);
    
    if (responseCode === 200) {
      const data = JSON.parse(responseText);
      Logger.log(`   🎯 Agente respondió: ${data.status}`);
      Logger.log(`   📝 Thread ID del agente: ${data.thread_id}`);
    } else {
      Logger.log(`   ⚠️  Respuesta inesperada: ${responseText}`);
    }
    
  } catch(e) {
    Logger.log(`❌ Error al enviar webhook: ${e.toString()}`);
  }
}

/**
 * Función para probar el webhook manualmente
 */
/*
function probarWebhookManual() {
  const testGcsPath = "gs://rpa_facturacion/entrada_facturas/test@ejemplo.com/123456789_test.pdf";
  const testRemitente = "proveedor@ejemplo.com";
  
  enviarWebhookAlAgente(testGcsPath, testRemitente, "Factura TEST", "test_thread_123");
}
*/

/**
 * Configurar trigger automático
 */
function configurarTrigger() {
  // Eliminar triggers existentes
  const triggers = ScriptApp.getProjectTriggers();
  triggers.forEach(trigger => ScriptApp.deleteTrigger(trigger));
  
  // Crear nuevo trigger que se ejecute cada 5 minutos
  ScriptApp.newTrigger('procesarCorreosYSubirAGCS')
    .timeBased()
    .everyMinutes(1)
    .create();
  
  Logger.log("✅ Trigger configurado: se ejecutará cada 5 minutos");
}
