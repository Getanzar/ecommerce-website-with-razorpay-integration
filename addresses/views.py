from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404

from .models import Address
from .forms import AddressForm


@login_required
def address_list(request):

    addresses = Address.objects.filter(
        user=request.user
    ).order_by("-is_default", "-id")

    return render(
        request,
        "addresses/address_list.html",
        {
            "addresses": addresses
        },
    )


@login_required
def add_address(request):

    if request.method == "POST":

        form = AddressForm(request.POST)

        if form.is_valid():

            address = form.save(commit=False)

            address.user = request.user

            if not Address.objects.filter(user=request.user).exists():
                address.is_default = True

            address.save()

            return redirect("address_list")

    else:

        form = AddressForm()

    return render(
        request,
        "addresses/address_form.html",
        {
            "form": form,
            "title": "Add Address",
        },
    )

@login_required
def edit_address(request, pk):

    address = get_object_or_404(
        Address,
        id=pk,
        user=request.user,
    )

    if request.method == "POST":

        form = AddressForm(
            request.POST,
            instance=address,
        )

        if form.is_valid():

            form.save()

            return redirect("address_list")

    else:

        form = AddressForm(instance=address)

    return render(
        request,
        "addresses/address_form.html",
        {
            "form": form,
            "title": "Edit Address",
        },
    )


@login_required
def delete_address(request, pk):

    address = get_object_or_404(
        Address,
        id=pk,
        user=request.user,
    )

    address.delete()

    return redirect("address_list")


@login_required
def default_address(request, pk):

    Address.objects.filter(
        user=request.user
    ).update(is_default=False)

    address = get_object_or_404(
        Address,
        id=pk,
        user=request.user,
    )

    address.is_default = True

    address.save()

    return redirect("address_list")