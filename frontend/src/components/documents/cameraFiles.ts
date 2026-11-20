export const cameraMimeTypes = [
  "image/jpeg",
  "image/png",
  "image/heic",
  "image/heif",
];
export const cameraAccept = `${cameraMimeTypes.join(",")},.jpg,.jpeg,.png,.heic,.heif`;
export const invalidPhotoMessage =
  "Wybierz niepuste zdjęcie w formacie JPG, PNG, HEIC lub HEIF.";

export function isCameraPhoto(file: File): boolean {
  return (
    file.size > 0 &&
    (cameraMimeTypes.includes(file.type) ||
      file.type === "" ||
      file.type === "application/octet-stream")
  );
}
