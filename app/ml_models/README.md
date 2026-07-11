# AgroGuide Disease Model

The plant disease model is no longer loaded by this Flask application.

Disease prediction now happens through the AWS-hosted Flask API configured with:

```dotenv
MODEL_API_URL=http://your-ec2-public-host-or-ip:5000/predict
MODEL_API_TIMEOUT_SECONDS=30
```

The app sends uploaded leaf images to `MODEL_API_URL` as `multipart/form-data`
with the file field named `image`.

Expected JSON response examples:

```json
{
  "success": true,
  "prediction": "Tomato___Late_blight",
  "confidence": 0.91
}
```

or:

```json
{
  "disease_class": "Tomato___Late_blight",
  "confidence_percent": 91.0,
  "advice": "Remove infected leaves and avoid overhead irrigation."
}
```

Additional fields are preserved and saved with scan history metadata.
