output "certificate_map" {
  value = google_certificate_manager_certificate_map.names.name
}

output "ingress_address_name" {
  value = google_compute_global_address.ingress.name
}

output "ingress_address" {
  value = google_compute_global_address.ingress.address
}

output "media_addresses" {
  value = { for world, address in google_compute_address.media : world => address.address }
}
