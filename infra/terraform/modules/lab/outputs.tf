output "name" {
  value = google_compute_instance.generator.name
}

output "internal_address" {
  value = google_compute_instance.generator.network_interface[0].network_ip
}

output "public_address" {
  value = google_compute_instance.generator.network_interface[0].access_config[0].nat_ip
}
